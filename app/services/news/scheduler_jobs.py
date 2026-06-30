"""Synchronous wrappers for async news crawlers.

Each wrapper is a thin facade that runs an async crawl and persists
results. The actual crawlers (xinhua/cninfo/sina/yahoo/cnbc/sec/reddit)
expose an async ``crawl()`` method; this module adds a thin DB-write
layer and exposes a sync function suitable for APScheduler.
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _run_async(coro: Any) -> Any:
    """Run an async coroutine on a reused event loop."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _write_to_db(articles: list) -> int:
    """Persist RawArticles into NewsArticle via the normalizer."""
    if not articles:
        return 0
    from app.core.database import SessionLocal
    from app.services.news.normalizer import NewsNormalizer

    db = SessionLocal()
    try:
        normalizer = NewsNormalizer(db)
        written = 0
        for raw in articles:
            try:
                article = normalizer.normalize(raw)
                if article is not None:
                    written += 1
            except Exception as exc:  # pragma: no cover
                logger.warning("normalizer failed for %s: %s", raw.url, exc)
        db.commit()
        return written
    except Exception as exc:
        db.rollback()
        logger.exception("DB commit failed: %s", exc)
        return 0
    finally:
        db.close()


# ── A-share ──

def run_xinhua_crawl() -> dict[str, int]:
    from app.services.news.sources.xinhua import XinhuaCrawler
    from app.services.news.normalizer import NewsNormalizer
    from app.core.database import SessionLocal

    async def _go():
        async with XinhuaCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("xinhua crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


def run_cninfo_crawl() -> dict[str, int]:
    from app.services.news.sources.cninfo import CninfoCrawler

    async def _go():
        async with CninfoCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("cninfo crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


def run_sina_crawl() -> dict[str, int]:
    from app.services.news.sources.sina import SinaCrawler

    async def _go():
        async with SinaCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("sina crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


# ── US ──

def run_yahoo_crawl() -> dict[str, int]:
    from app.services.news.sources.yahoo_rss import YahooFinanceCrawler

    async def _go():
        async with YahooFinanceCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("yahoo crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


def run_cnbc_crawl() -> dict[str, int]:
    from app.services.news.sources.cnbc import CNBCCrawler

    async def _go():
        async with CNBCCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("cnbc crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


def run_sec_edgar_crawl() -> dict[str, int]:
    from app.services.news.sources.sec_edgar import SecEdgarCrawler

    async def _go():
        async with SecEdgarCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("sec_edgar crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


def run_reddit_crawl() -> dict[str, int]:
    from app.services.news.sources.reddit import RedditCrawler

    async def _go():
        async with RedditCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("reddit crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}