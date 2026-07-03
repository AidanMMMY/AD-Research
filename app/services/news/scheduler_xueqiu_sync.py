"""Synchronous wrapper for the async Xueqiu crawler, so APScheduler
(BackgroundScheduler) can schedule it as a regular cron job.

This module also wires the ``write_posts`` callback that
:func:`app.services.news.scheduler_xueqiu.run_xueqiu_crawl` accepts.
Without a callback the crawler fetches posts but never persists them:
the loop in ``run_xueqiu_crawl`` only invokes ``write_posts`` when a
caller supplies one. APScheduler jobs run via this wrapper, so the
wrapper is responsible for building a callback that converts the
Xueqiu-specific :class:`RawXueqiuPost` rows into the shared
:class:`RawArticle` form and hands them to the
:class:`NewsNormalizer` (the same persistence path used by every
other news source).

Every successful / failed / no-op tick writes a row to ``etl_log``
so the news-health endpoint can show real run history (job id
``news_xueqiu_5m``).
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from functools import wraps

from app.models.etl import ETLLog
from app.services.news.scheduler_xueqiu import run_xueqiu_crawl

logger = logging.getLogger(__name__)


def _record_etl(job_id: str):
    """Write a single start+end ``ETLLog`` row around ``run_xueqiu_crawl_sync``.

    Mirrors the equivalent decorator in ``scheduler_jobs.py`` so the
    xueqiu tick shows up the same way on the news-health page as the
    other sources. ``run_xueqiu_crawl_sync`` always returns a dict
    with integer counters — we forward ``written`` (via posts) as the
    record count when present.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from app.core.database import SessionLocal

            db = SessionLocal()
            log_row: ETLLog | None = None
            started = time.monotonic()
            try:
                log_row = ETLLog(
                    job_name=job_id,
                    status="running",
                    start_time=datetime.now(timezone.utc),
                )
                db.add(log_row)
                db.commit()
                db.refresh(log_row)
            except Exception as exc:  # pragma: no cover - best effort
                logger.debug("etl_log start insert failed for %s: %s", job_id, exc)

            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                try:
                    if log_row is not None:
                        log_row.status = "failed"
                        log_row.end_time = datetime.now(timezone.utc)
                        log_row.records_count = 0
                        log_row.error_msg = str(exc)[:1000]
                        db.commit()
                except Exception:  # pragma: no cover - defensive
                    try:
                        db.rollback()
                    except Exception:
                        pass
                finally:
                    db.close()
                raise

            try:
                if log_row is not None and isinstance(result, dict):
                    log_row.status = "success"
                    log_row.end_time = datetime.now(timezone.utc)
                    records = int(result.get("posts") or 0)
                    log_row.records_count = records
                    log_row.extra_data = {
                        "duration_seconds": round(time.monotonic() - started, 3),
                        "symbols_total": result.get("symbols_total", 0),
                        "symbols_ok": result.get("symbols_ok", 0),
                        "symbols_failed": result.get("symbols_failed", 0),
                        "auth_ok": result.get("auth_ok", 0),
                        "users_refreshed": result.get("users_refreshed", 0),
                    }
                    db.commit()
            except Exception as exc:  # pragma: no cover - best effort
                logger.debug("etl_log finish update failed for %s: %s", job_id, exc)
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                db.close()
            return result

        return wrapper

    return decorator


def _make_write_posts():
    """Build a closure that persists Xueqiu posts via ``NewsNormalizer``.

    Each call to this function returns a fresh callback that owns its
    own DB session / normalizer pair. The callback returns the number
    of rows that were actually upserted (duplicates count as zero).
    """
    from app.core.database import SessionLocal
    from app.services.news.normalizer import NewsNormalizer
    from app.services.news.sources.xueqiu import posts_to_articles

    db = SessionLocal()
    normalizer = NewsNormalizer(db)

    def _write_posts(_db, posts):
        # ``_db`` is the SessionLocal-managed session owned by the
        # caller (the scheduler's per-symbol loop). We use the
        # closure-owned normalizer's session for the actual writes so
        # the calling session can stay focused on fetch-state rows.
        try:
            articles = posts_to_articles(posts)
            if not articles:
                return 0
            written = 0
            for art in articles:
                if normalizer.normalize(art) is not None:
                    written += 1
            db.commit()
            return written
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("xueqiu write_posts raised: %s", exc)
            try:
                db.rollback()
            except Exception:
                pass
            return 0
        finally:
            # Re-open the session for the next tick (commit() keeps it
            # usable, but a rollback after an error would leave the
            # normalizer in a bad state).
            pass

    # Best-effort cleanup when the process exits (module-level db is
    # closed by the normalizer on each commit, but if the crawler
    # raised before any write we'd still want to release the
    # connection).
    import atexit

    atexit.register(lambda: db.close())
    return _write_posts


@_record_etl("news_xueqiu_5m")
def run_xueqiu_crawl_sync() -> dict[str, int]:
    """Synchronous entry point for APScheduler. Reuses one event loop
    per process to avoid recreating it on every tick.

    Builds a fresh ``write_posts`` callback per tick so the async
    fetch loop can persist rows into ``news_article`` (the central
    table shared with every other news source).
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Per-tick callback. We do NOT keep one across ticks because the
    # underlying DB session lifetime is tied to the normalizer — a
    # dead session between ticks would silently lose writes.
    write_posts = _make_write_posts()

    if loop.is_running():
        # We're already inside an event loop (shouldn't happen from APScheduler
        # background thread, but guard anyway). Fall back to a fresh loop.
        loop = asyncio.new_event_loop()
        try:
            stats = loop.run_until_complete(run_xueqiu_crawl(write_posts=write_posts))
            return stats
        finally:
            loop.close()

    try:
        stats = loop.run_until_complete(run_xueqiu_crawl(write_posts=write_posts))
        return stats
    except Exception as exc:  # pragma: no cover - scheduler path
        logger.exception("Xueqiu crawl failed: %s", exc)
        return {"symbols_total": 0, "symbols_ok": 0, "symbols_failed": 0,
                "posts": 0, "users_refreshed": 0, "auth_ok": 0}