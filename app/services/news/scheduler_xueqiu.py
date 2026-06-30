"""Background scheduler for the Xueqiu crawler.

The job is registered in :func:`init_scheduler` and runs every 5
minutes. Each tick:

1. Validates the Xueqiu cookie (single lightweight probe). If invalid,
   the tick is skipped without touching the database.
2. Picks ``batch_size`` symbols from the active ``etf_info`` table,
   rotating through the watchlist in round-robin order so that
   lower-priority symbols are still seen eventually.
3. Fetches the public timeline for each symbol and forwards the
   normalised posts to ``write_posts`` (an Agent-B-owned callback we
   import lazily so this module can load before ``news_article`` is in
   place). The callback is responsible for any DB writes; the
   scheduler itself only records fetch-state + user-cache rows.
4. Updates ``xueqiu_fetch_state`` and ``xueqiu_user_cache`` rows.

The scheduler never auto-logs in and never writes raw posts directly
into ``xueqiu_*`` tables — only operational state lives there. Raw
posts go to the central ``news_article`` table via the Agent-B writer.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.database import SessionLocal
from app.core.redis_client import redis_lock
from app.models.etf import ETFInfo
from app.models.news import XueqiuFetchState, XueqiuUserCache
from app.services.news.sources.xueqiu import (
    RawXueqiuPost,
    XueqiuCrawler,
    to_xueqiu_symbol,
)
from app.services.news.sources.xueqiu_auth import XueqiuAuth, XueqiuAuthError

logger = logging.getLogger(__name__)


_LOCK_NAME = "xueqiu_crawler"

# Markets the crawler actively scrapes. Crypto / FX are skipped because
# Xueqiu's $...$ convention rarely covers them.
_WATCHLIST_MARKETS: tuple[str, ...] = ("A股", "US", "HK")


# ---------------------------------------------------------------------------
# Watchlist selection
# ---------------------------------------------------------------------------


def _select_watchlist(
    db: Session,
    *,
    batch_size: int,
    last_seen: dict[str, datetime] | None = None,
) -> list[str]:
    """Pick ``batch_size`` symbols to scrape on this tick.

    Round-robins over the active watchlist using the most-recent fetch
    timestamp (``xueqiu_fetch_state.last_fetched_at``) as the sort key —
    the symbols fetched longest ago come first, with never-fetched
    symbols sorted ahead of recent ones.
    """
    stmt = select(ETFInfo.code).where(
        ETFInfo.status == "active",
        ETFInfo.market.in_(_WATCHLIST_MARKETS),
    )
    rows = db.execute(stmt).scalars().all()
    if not rows:
        return []

    if last_seen:
        rows = sorted(rows, key=lambda c: (last_seen.get(c) or datetime.min.replace(tzinfo=timezone.utc), c))

    return list(rows[:batch_size])


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _record_fetch_state(
    db: Session,
    *,
    symbol: str,
    newest_id: int | None,
    oldest_id: int | None,
    status: str,
    error: str | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    next_at = now + timedelta(minutes=5)
    row = db.get(XueqiuFetchState, symbol)
    if row is None:
        row = XueqiuFetchState(
            symbol=symbol,
            last_max_id=oldest_id,
            last_newest_id=newest_id,
            last_fetched_at=now,
            next_fetch_at=next_at,
            last_status=status,
            last_error=error,
            fetch_count=1,
        )
        db.add(row)
    else:
        if oldest_id is not None:
            row.last_max_id = oldest_id
        if newest_id is not None:
            row.last_newest_id = newest_id
        row.last_fetched_at = now
        row.next_fetch_at = next_at
        row.last_status = status
        row.last_error = error
        row.fetch_count = (row.fetch_count or 0) + 1
    db.commit()


def _record_user(
    db: Session,
    *,
    user_id: int,
    payload: dict[str, Any],
) -> None:
    row = db.get(XueqiuUserCache, user_id)
    if row is None:
        row = XueqiuUserCache(user_id=user_id)
        db.add(row)
    row.screen_name = payload.get("screen_name") or (row.screen_name if row else None)
    row.followers_count = payload.get("followers_count") or (row.followers_count if row else None)
    row.friends_count = payload.get("friends_count") or (row.friends_count if row else None)
    row.status_count = payload.get("status_count") or (row.status_count if row else None)
    row.description = payload.get("description") or (row.description if row else None)
    row.verified = bool(payload.get("verified")) if payload.get("verified") is not None else (row.verified if row else False)
    db.commit()


def _user_cache_is_fresh(db: Session, user_id: int, *, ttl_days: int) -> bool:
    row = db.get(XueqiuUserCache, user_id)
    if row is None or row.fetched_at is None:
        return False
    return (datetime.now(timezone.utc) - row.fetched_at) < timedelta(days=ttl_days)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_xueqiu_crawl(
    *,
    write_posts: Callable[[Session, list[RawXueqiuPost]], int] | None = None,
) -> dict[str, int]:
    """Run a single Xueqiu fetch tick.

    Returns a small dict of counters for the scheduler log. Designed to
    be safe to invoke concurrently across multiple workers (a Redis lock
    serialises actual fetching).
    """
    settings = get_settings()
    batch_size = max(1, int(settings.xueqiu_batch_size or 50))
    per_minute = max(1, int(settings.xueqiu_per_minute or 30))
    user_ttl_days = max(1, int(settings.xueqiu_user_cache_ttl_days or 7))

    stats: dict[str, int] = {
        "symbols_total": 0,
        "symbols_ok": 0,
        "symbols_failed": 0,
        "posts": 0,
        "users_refreshed": 0,
        "auth_ok": 0,
    }

    with redis_lock(_LOCK_NAME, expire_seconds=600) as acquired:
        if not acquired:
            logger.info("Xueqiu crawler skipped: lock in use")
            return stats

        # 1) Probe cookie before doing any real work.
        try:
            auth = XueqiuAuth(settings.xueqiu_cookie or "")
        except XueqiuAuthError as exc:
            logger.warning("Xueqiu auth unavailable, skipping tick: %s", exc)
            return stats

        if not await auth.wait_until_valid(attempts=1, backoff_seconds=0):
            logger.warning("Xueqiu cookie invalid; skipping tick")
            return stats
        stats["auth_ok"] = 1

        # 2) Pick symbols.
        db = SessionLocal()
        try:
            last_seen_rows = db.execute(
                select(XueqiuFetchState.symbol, XueqiuFetchState.last_fetched_at)
            ).all()
            last_seen = {sym: ts for sym, ts in last_seen_rows if ts is not None}
            watchlist = _select_watchlist(db, batch_size=batch_size, last_seen=last_seen)
        finally:
            db.close()
        stats["symbols_total"] = len(watchlist)
        if not watchlist:
            return stats

        # 3) Fetch each symbol.
        crawler = XueqiuCrawler(
            auth=auth,
            per_minute=per_minute,
            posts_per_symbol=int(settings.xueqiu_posts_per_symbol or 20),
            comments_per_post=0,
        )

        for symbol in watchlist:
            db = SessionLocal()
            try:
                try:
                    posts = await crawler.fetch_symbol(symbol)
                except XueqiuAuthError as exc:
                    logger.warning("Xueqiu auth failed mid-tick, aborting: %s", exc)
                    _record_fetch_state(
                        db,
                        symbol=symbol,
                        newest_id=None,
                        oldest_id=None,
                        status="auth_failed",
                        error=str(exc),
                    )
                    stats["symbols_failed"] += 1
                    return stats
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Xueqiu fetch failed for %s: %s", symbol, exc)
                    _record_fetch_state(
                        db,
                        symbol=symbol,
                        newest_id=None,
                        oldest_id=None,
                        status="error",
                        error=str(exc)[:500],
                    )
                    stats["symbols_failed"] += 1
                    continue

                stats["symbols_ok"] += 1
                stats["posts"] += len(posts)

                # Persist raw posts via the writer callback (Agent B).
                if write_posts is not None and posts:
                    try:
                        write_posts(db, posts)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Post writer raised for %s: %s", symbol, exc)

                # Update fetch-state with the new cursor.
                newest_id = _safe_int(posts[0].source_id) if posts else None
                oldest_id = _safe_int(posts[-1].source_id) if posts else None
                _record_fetch_state(
                    db,
                    symbol=symbol,
                    newest_id=newest_id,
                    oldest_id=oldest_id,
                    status="ok",
                )

                # Refresh user cache for new authors (best effort).
                if posts:
                    await _refresh_user_cache(
                        db, crawler, posts, ttl_days=user_ttl_days,
                        on_record=lambda payload: _record_user(
                            db,
                            user_id=int(payload["id"]),
                            payload=payload,
                        ),
                        on_refreshed=lambda: stats.__setitem__("users_refreshed", stats["users_refreshed"] + 1),
                    )
            finally:
                db.close()

    return stats


# ---------------------------------------------------------------------------
# User cache refresh
# ---------------------------------------------------------------------------


async def _refresh_user_cache(
    db: Session,
    crawler: XueqiuCrawler,
    posts: Iterable[RawXueqiuPost],
    *,
    ttl_days: int,
    on_record: Callable[[dict[str, Any]], None],
    on_refreshed: Callable[[], None],
) -> None:
    """For each post author, ensure ``XueqiuUserCache`` is fresh.

    Honours the per-minute rate limit and the cache TTL — only fetches
    the user profile if it is missing or older than ``ttl_days``.
    """
    for post in posts:
        if not post.author_id:
            continue
        if _user_cache_is_fresh(db, post.author_id, ttl_days=ttl_days):
            continue
        try:
            payload = await crawler.fetch_user(post.author_id)
        except XueqiuAuthError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.debug("User fetch failed for %s: %s", post.author_id, exc)
            continue
        if not isinstance(payload, dict):
            continue
        # /v4/users/show.json nests the user under "user" on some
        # responses; unwrap defensively.
        user_payload = payload.get("user") if isinstance(payload.get("user"), dict) else payload
        if not user_payload.get("id"):
            continue
        try:
            on_record(user_payload)
            on_refreshed()
        except Exception as exc:  # noqa: BLE001
            logger.debug("User cache upsert failed for %s: %s", user_payload.get("id"), exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# Allow running the tick in isolation for unit tests / manual debug.
if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_xueqiu_crawl())
