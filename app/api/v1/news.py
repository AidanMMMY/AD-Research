"""News API routes.

Exposes the ``news_article`` and ``news_article_symbol`` tables for
frontend consumers:

* ``GET  /news``                          — list + filter + paginate
* ``GET  /news/watchlist``                — list scoped to the user's favorites
* ``GET  /news/{article_id}``             — detail + linked symbols
* ``GET  /news/stats/sources``            — per-source ingestion volume (last 7d)
* ``GET  /news/health``                   — per-source diagnostics + scheduler status
* ``POST /news/{article_id}/fetch-content``  — Jina Reader full-text fetch
* ``POST /news/{article_id}/translate``   — DeepSeek translate (en → zh), cached

All routes require a valid JWT. Crawler / scheduler backends hit the
DB directly via :mod:`app.services.news.normalizer` — these endpoints
are read-only (apart from the two POSTs above, which only fill derived
cache columns).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import redis
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config import get_settings
from app.core.redis_client import get_redis_client, redis_lock
from app.core.scheduler import get_scheduler_jobs, is_scheduler_running
from app.models.etl import ETLLog
from app.models.favorite import UserFavorite
from app.schemas.auth import UserResponse
from app.services.news._model_loader import NewsArticle, NewsArticleSymbol
from app.services.news.content_fetcher import ContentFetcher
from app.services.news.translation_service import NewsTranslationService

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["news"],
    dependencies=[Depends(get_current_user)],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso_utc(value: datetime | None) -> str | None:
    """Serialize a datetime as an explicit UTC ISO-8601 string.

    The ``news_article.published_at`` / ``fetched_at`` columns are
    stored as naive UTC values (the SQLAlchemy column type is plain
    ``DateTime`` without tz, but every crawler normalises to UTC in
    :class:`RawArticle` before insert). When those naive values flow
    through ``datetime.isoformat()`` they come out without a timezone
    suffix, which the frontend then interprets as local time and
    displays 8 hours late for Asia/Shanghai users.

    Always emit a ``+00:00`` suffix so the API contract is unambiguous:
    every datetime field returned by this router is UTC.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    # ``timespec='seconds'`` keeps the wire format compact while still
    # giving the frontend a sub-minute resolution.
    return value.isoformat(timespec="seconds")


def _article_to_dict(article: NewsArticle, symbols: list[str] | None = None) -> dict:
    """Render a :class:`NewsArticle` row as a JSON-safe dict."""
    return {
        "id": article.id,
        "source": article.source,
        "source_id": article.source_id,
        "url": article.url,
        "title": article.title,
        "summary": article.summary,
        "author": article.author,
        "language": article.language,
        "market": article.market,
        "category": article.category,
        "published_at": _iso_utc(article.published_at),
        "fetched_at": _iso_utc(article.fetched_at),
        "engagement": article.engagement or {},
        "sentiment_score": article.sentiment_score,
        "sentiment_label": article.sentiment_label,
        "symbols": symbols or [],
        # Cache slots for the Jina Reader lazy-load feature. The
        # ``summary`` fallback covers the case where the user never
        # clicked the load button.
        "full_content": article.full_content,
        "full_content_fetched_at": _iso_utc(article.full_content_fetched_at),
        # Chinese translation cache (only populated for English articles;
        # the ``/translate`` endpoint enforces ``language == 'en'``).
        "translated_zh": article.translated_zh,
        "translation_generated_at": _iso_utc(article.translation_generated_at),
    }


def _parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 datetime string. Returns ``None`` for empty/invalid."""
    if not value:
        return None
    try:
        # ``datetime.fromisoformat`` handles "Z" suffix only on 3.11+.
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
def list_news(
    market: str | None = Query(None, description="Filter by market (cn_a | us | crypto)"),
    symbol: str | None = Query(None, description="Filter by linked instrument code"),
    source: str | None = Query(None, description="Filter by source id (e.g. xinhua_rss)"),
    from_date: str | None = Query(None, description="ISO-8601 lower bound on published_at"),
    to_date: str | None = Query(None, description="ISO-8601 upper bound on published_at"),
    page: int = Query(1, ge=1, description="1-indexed page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size (1-100)"),
    db: Session = Depends(get_db),
) -> dict:
    """List news articles with optional filters and pagination."""
    from_dt = _parse_iso(from_date)
    to_dt = _parse_iso(to_date)
    if from_date and from_dt is None:
        raise HTTPException(status_code=400, detail="from_date must be ISO-8601")
    if to_date and to_dt is None:
        raise HTTPException(status_code=400, detail="to_date must be ISO-8601")

    stmt = select(NewsArticle)
    count_stmt = select(func.count(NewsArticle.id))

    if market:
        stmt = stmt.where(NewsArticle.market == market)
        count_stmt = count_stmt.where(NewsArticle.market == market)
    if source:
        stmt = stmt.where(NewsArticle.source == source)
        count_stmt = count_stmt.where(NewsArticle.source == source)
    if from_dt is not None:
        stmt = stmt.where(NewsArticle.published_at >= from_dt)
        count_stmt = count_stmt.where(NewsArticle.published_at >= from_dt)
    if to_dt is not None:
        stmt = stmt.where(NewsArticle.published_at <= to_dt)
        count_stmt = count_stmt.where(NewsArticle.published_at <= to_dt)
    if symbol:
        # Subquery for the linked-symbol filter.
        sub = (
            select(NewsArticleSymbol.article_id)
            .where(NewsArticleSymbol.symbol == symbol)
            .subquery()
        )
        stmt = stmt.where(NewsArticle.id.in_(select(sub.c.article_id)))
        count_stmt = count_stmt.where(NewsArticle.id.in_(select(sub.c.article_id)))

    total = db.execute(count_stmt).scalar() or 0
    rows = db.execute(
        stmt.order_by(NewsArticle.published_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()

    items = [_article_to_dict(row) for row in rows]
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": int(total),
        "total_pages": (int(total) + page_size - 1) // page_size if total else 0,
    }


@router.get("/watchlist")
def list_watchlist_news(
    market: str | None = Query(None, description="Filter by market (cn_a | us | crypto)"),
    source: str | None = Query(None, description="Filter by source id (e.g. xinhua_rss)"),
    from_date: str | None = Query(None, description="ISO-8601 lower bound on published_at"),
    to_date: str | None = Query(None, description="ISO-8601 upper bound on published_at"),
    page: int = Query(1, ge=1, description="1-indexed page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size (1-100)"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    """List news articles linked to the current user's favorites.

    Joins ``news_article_symbol`` against the user's ``user_favorite``
    rows. The response shape mirrors ``GET /news`` plus a ``watchlist``
    block that reports how many symbols were used and how many of them
    have at least one matching article — useful for surfacing
    "5 favorites, 28 articles" in the UI.
    """
    from_dt = _parse_iso(from_date)
    to_dt = _parse_iso(to_date)
    if from_date and from_dt is None:
        raise HTTPException(status_code=400, detail="from_date must be ISO-8601")
    if to_date and to_dt is None:
        raise HTTPException(status_code=400, detail="to_date must be ISO-8601")

    # Resolve the user's favorite codes up-front. An empty watchlist is
    # a legitimate state — return an empty page rather than 404 so the
    # frontend can render an empty-state.
    favorite_codes = [
        row[0]
        for row in db.execute(
            select(UserFavorite.etf_code).where(UserFavorite.username == user.username)
        ).all()
    ]
    if not favorite_codes:
        return {
            "items": [],
            "page": page,
            "page_size": page_size,
            "total": 0,
            "total_pages": 0,
            "watchlist": {
                "symbols": [],
                "symbols_with_news": 0,
                "total_articles": 0,
            },
        }

    # Subquery: article ids linked to any favorite code.
    linked_sub = (
        select(NewsArticleSymbol.article_id)
        .where(NewsArticleSymbol.symbol.in_(favorite_codes))
        .distinct()
        .subquery()
    )

    stmt = select(NewsArticle).where(NewsArticle.id.in_(select(linked_sub.c.article_id)))
    count_stmt = (
        select(func.count(NewsArticle.id))
        .where(NewsArticle.id.in_(select(linked_sub.c.article_id)))
    )

    if market:
        stmt = stmt.where(NewsArticle.market == market)
        count_stmt = count_stmt.where(NewsArticle.market == market)
    if source:
        stmt = stmt.where(NewsArticle.source == source)
        count_stmt = count_stmt.where(NewsArticle.source == source)
    if from_dt is not None:
        stmt = stmt.where(NewsArticle.published_at >= from_dt)
        count_stmt = count_stmt.where(NewsArticle.published_at >= from_dt)
    if to_dt is not None:
        stmt = stmt.where(NewsArticle.published_at <= to_dt)
        count_stmt = count_stmt.where(NewsArticle.published_at <= to_dt)

    total = db.execute(count_stmt).scalar() or 0
    rows = db.execute(
        stmt.order_by(NewsArticle.published_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()

    # For each fetched article, hydrate its symbols so the frontend can
    # render them inline. We only need symbols for the current page,
    # not the whole result set.
    article_ids = [row.id for row in rows]
    symbols_by_article: dict[int, list[str]] = {aid: [] for aid in article_ids}
    if article_ids:
        sym_rows = db.execute(
            select(NewsArticleSymbol.article_id, NewsArticleSymbol.symbol).where(
                NewsArticleSymbol.article_id.in_(article_ids)
            )
        ).all()
        for aid, sym in sym_rows:
            symbols_by_article.setdefault(aid, []).append(sym)

    items = [_article_to_dict(row, symbols=symbols_by_article.get(row.id, [])) for row in rows]

    # Per-favorite coverage count — how many of the user's symbols
    # actually have at least one matching article within the current
    # filters. Used by the UI for the "自选标的 X 个 · 相关资讯 Y 条"
    # summary. We respect the same market/source/date filters so the
    # number tracks what the user is actually seeing on the page.
    covered_q = (
        select(NewsArticleSymbol.symbol)
        .join(NewsArticle, NewsArticle.id == NewsArticleSymbol.article_id)
        .where(NewsArticleSymbol.symbol.in_(favorite_codes))
    )
    if market:
        covered_q = covered_q.where(NewsArticle.market == market)
    if source:
        covered_q = covered_q.where(NewsArticle.source == source)
    if from_dt is not None:
        covered_q = covered_q.where(NewsArticle.published_at >= from_dt)
    if to_dt is not None:
        covered_q = covered_q.where(NewsArticle.published_at <= to_dt)
    covered_set = {sym for (sym,) in db.execute(covered_q.distinct()).all()}

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": int(total),
        "total_pages": (int(total) + page_size - 1) // page_size if total else 0,
        "watchlist": {
            "symbols": favorite_codes,
            "symbols_with_news": len(covered_set),
            "total_articles": int(total),
        },
    }


@router.get("/stats/sources")
def source_stats(db: Session = Depends(get_db)) -> dict:
    """Per-source ingestion counts for the last 7 days.

    Returns a dict ``{source: {total, last_7d, last_24h}}`` sorted by
    total descending. The numbers come straight from
    ``news_article.fetched_at`` so they reflect rows that were
    actually persisted.
    """
    now = datetime.now(tz=timezone.utc)
    cutoff_7d = now - timedelta(days=7)
    cutoff_24h = now - timedelta(hours=24)

    rows = db.execute(
        select(
            NewsArticle.source,
            func.count(NewsArticle.id).label("total"),
            func.sum(
                case((NewsArticle.fetched_at >= cutoff_7d, 1), else_=0)
            ).label("last_7d"),
            func.sum(
                case((NewsArticle.fetched_at >= cutoff_24h, 1), else_=0)
            ).label("last_24h"),
        )
        .group_by(NewsArticle.source)
        .order_by(func.count(NewsArticle.id).desc())
    ).all()

    sources: list[dict[str, Any]] = []
    for source, total, last_7d, last_24h in rows:
        sources.append(
            {
                "source": source,
                "total": int(total or 0),
                "last_7d": int(last_7d or 0),
                "last_24h": int(last_24h or 0),
            }
        )
    return {
        "as_of": now.isoformat(),
        "sources": sources,
    }


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

# News source identifiers used in ``NewsArticle.source``. Kept in sync
# with ``app/services/news/sources/*.py`` ``source_name`` declarations.
# NOTE: xinhua_rss is temporarily omitted because its public RSS endpoints
# return 404.
_NEWS_SOURCES: list[str] = [
    "cninfo",
    "sina_finance",
    "wechat_zeping",
    "yahoo_finance",
    "cnbc",
    "sec_edgar",
    "reddit",
    "xueqiu",
    "coindesk",
    "cointelegraph",
]

# Map each NewsArticle source to the scheduler job_id (defined in
# ``app/core/scheduler.py``). Used to look up the latest ETL log row
# for that job.
_SOURCE_TO_JOB: dict[str, str] = {
    "cninfo": "news_cninfo_10m",
    "sina_finance": "news_sina_5m",
    "wechat_zeping": "news_wechat_zeping_15m",
    "yahoo_finance": "news_yahoo_5m",
    "cnbc": "news_cnbc_5m",
    "sec_edgar": "news_sec_edgar_30m",
    "reddit": "news_reddit_5m",
    "xueqiu": "news_xueqiu_5m",
    "coindesk": "news_coindesk_5m",
    "cointelegraph": "news_cointelegraph_5m",
}


def _source_health_row(db: Session, source: str) -> dict[str, Any]:
    """Build the diagnostics row for a single NewsArticle source."""
    now = datetime.now(tz=timezone.utc)
    cutoff_24h = now - timedelta(hours=24)

    # Aggregate total + last 24h + latest published_at + latest fetched_at
    # in a single query so we don't N+1 the DB.
    agg_row = db.execute(
        select(
            func.count(NewsArticle.id).label("total"),
            func.sum(case((NewsArticle.fetched_at >= cutoff_24h, 1), else_=0)).label(
                "last_24h"
            ),
            func.max(NewsArticle.published_at).label("last_published_at"),
            func.max(NewsArticle.fetched_at).label("last_fetched_at"),
        ).where(NewsArticle.source == source)
    ).one()

    total = int(agg_row.total or 0)
    last_24h = int(agg_row.last_24h or 0)
    last_published_at = agg_row.last_published_at
    last_fetched_at = agg_row.last_fetched_at

    # Latest etl_log row for the matching scheduler job (if any).
    job_id = _SOURCE_TO_JOB.get(source)
    etl: dict[str, Any] | None = None
    if job_id:
        last_run = (
            db.query(ETLLog)
            .filter(ETLLog.job_name == job_id)
            .order_by(desc(ETLLog.created_at))
            .first()
        )
        if last_run is not None:
            etl = {
                "status": last_run.status,
                "records": last_run.records_count,
                "error_msg": last_run.error_msg,
                "finished_at": _iso_utc(last_run.end_time),
                "started_at": _iso_utc(last_run.start_time),
            }

    return {
        "source": source,
        "job_id": job_id,
        "total": total,
        "last_24h": last_24h,
        "last_published_at": _iso_utc(last_published_at),
        "last_fetched_at": _iso_utc(last_fetched_at),
        "latest_etl": etl,
    }


@router.get("/health")
def news_health(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Per-source diagnostic: latest article time + 24h count + scheduler status.

    Used by the ``NewsHealth`` operations dashboard. Returns gracefully
    even when the scheduler is dead (the dashboard then renders
    ``scheduler_running=false`` and the source rows stay red).
    """
    now = datetime.now(tz=timezone.utc)

    sources = [_source_health_row(db, src) for src in _NEWS_SOURCES]

    # Scheduler introspection — safe even when the BackgroundScheduler
    # was never started (returns empty list + running=false).
    scheduler_running = is_scheduler_running()
    scheduler_jobs = get_scheduler_jobs()
    news_jobs = [
        j for j in scheduler_jobs if j["id"].startswith("news_")
    ]

    return {
        "as_of": now.isoformat(),
        "scheduler_running": scheduler_running,
        "scheduler_jobs": news_jobs,
        "scheduler_total_jobs": len(scheduler_jobs),
        "sources": sources,
    }
@router.get("/{article_id}")
def get_article(article_id: int, db: Session = Depends(get_db)) -> dict:
    """Return a single article plus its linked symbols."""
    article = db.get(NewsArticle, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail=f"article {article_id} not found")
    symbol_rows = db.execute(
        select(NewsArticleSymbol.symbol).where(NewsArticleSymbol.article_id == article_id)
    ).all()
    symbols = [s[0] for s in symbol_rows]
    return _article_to_dict(article, symbols=symbols)


@router.post("/{article_id}/fetch-content")
def fetch_article_content(
    article_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Fetch the full article body via Jina Reader and cache it.

    Returns ``{success, content, cached, error}``. On failure the
    caller (the frontend detail page) should fall back to ``body`` /
    ``summary`` already present on the article.

    Requires auth (``get_current_user`` is wired by the router-level
    ``dependencies``). Triggers a real network call — see
    :class:`app.services.news.content_fetcher.ContentFetcher`.
    """
    article = db.get(NewsArticle, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail=f"article {article_id} not found")

    fetcher = ContentFetcher(db)
    result = fetcher.fetch(article_id)

    if not result.success:
        # 502 lets the frontend distinguish "Jina failed" from a 404.
        # We still echo the article's intro/summary so the user has
        # something to read instead of a broken page.
        return {
            "success": False,
            "cached": False,
            "content": article.summary or article.body,
            "error": result.error or "unknown error",
        }

    return {
        "success": True,
        "cached": result.cached,
        "content": result.content,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Translation (en → zh, DeepSeek)
# ---------------------------------------------------------------------------


@router.post("/{article_id}/translate")
def translate_article(
    article_id: int,
    target_language: str = Query(
        "zh", description="Target language code (only 'zh' is supported in v1)"
    ),
    db: Session = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> dict:
    """Translate an English news article to Chinese via DeepSeek.

    Mirrors the ``/research-reports/{id}/summarize`` flow:

    * Per-user daily counter in Redis (24h TTL, fail-open if Redis is
      down) capped at ``news_translate_daily_limit``.
    * 60s Redis lock to serialize concurrent translate calls so two
      users clicking the button at the same time don't both hit the LLM.
    * The translation is persisted on ``news_article.translated_zh`` so
      a second call is a cache hit (no LLM cost, no rate-limit burn).

    Returns ``{translation, cached, tokens_used, generated_at,
    source_language, target_language}``. Errors:

    * 404 — article not found
    * 400 — non-English article, empty body, or unsupported target
    * 429 — daily limit exceeded
    * 409 — concurrent translate already in progress
    * 502 — DeepSeek call failed (no key, timeout, 5xx…)
    """
    # Per-user daily counter. Keyed by user + ISO date so it rolls
    # over at midnight UTC. Redis-down → fail-open (logged + skip).
    daily_limit = get_settings().news_translate_daily_limit
    today = date.today().isoformat()
    counter_key = f"news_translate_user:{current_user.id}:{today}"
    try:
        redis_client = get_redis_client()
        current = redis_client.incr(counter_key)
        if current == 1:
            redis_client.expire(counter_key, 86400)
        if current > daily_limit:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"今日翻译次数已达上限（{daily_limit} 次），"
                    "明天 0 点重置"
                ),
            )
    except redis.RedisError as exc:
        logger.warning("news_translate rate-limit unavailable (Redis error): %s", exc)
    except HTTPException:
        raise

    with redis_lock(f"news_translate:{article_id}", expire_seconds=60) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=409,
                detail="该文章正在翻译中，请稍后再试",
            )
        service = NewsTranslationService(db)
        try:
            result = service.translate(article_id, target_language=target_language)
        except ValueError as exc:
            msg = str(exc)
            if "not found" in msg:
                raise HTTPException(status_code=404, detail=msg)
            # Language / empty-body / unsupported target — all client errors.
            raise HTTPException(status_code=400, detail=msg)
        except RuntimeError as exc:
            # Provider unavailable / LLM call failed.
            raise HTTPException(status_code=502, detail=str(exc))
        return result


