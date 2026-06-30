"""Synchronous wrapper for the async Xueqiu crawler, so APScheduler
(BackgroundScheduler) can schedule it as a regular cron job.
"""

import asyncio
import logging

from app.services.news.scheduler_xueqiu import run_xueqiu_crawl

logger = logging.getLogger(__name__)


def run_xueqiu_crawl_sync() -> dict[str, int]:
    """Synchronous entry point for APScheduler. Reuses one event loop
    per process to avoid recreating it on every tick.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        # We're already inside an event loop (shouldn't happen from APScheduler
        # background thread, but guard anyway). Fall back to a fresh loop.
        loop = asyncio.new_event_loop()
        try:
            stats = loop.run_until_complete(run_xueqiu_crawl())
            return stats
        finally:
            loop.close()

    try:
        stats = loop.run_until_complete(run_xueqiu_crawl())
        return stats
    except Exception as exc:  # pragma: no cover - scheduler path
        logger.exception("Xueqiu crawl failed: %s", exc)
        return {"symbols_total": 0, "symbols_ok": 0, "symbols_failed": 0,
                "posts": 0, "users_refreshed": 0, "auth_ok": 0}