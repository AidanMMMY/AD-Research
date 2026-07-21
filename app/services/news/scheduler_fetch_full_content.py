"""Scheduled job to fetch full content for news articles.

Runs after the Xueqiu crawler to fetch and clean article content
using the tiered pipeline in ``content_fetcher`` (local trafilatura →
Jina Reader → LLM fallback).

M22-3 (2026-07-05) observability: every fetch now records the
AI-cleanup outcome (``ai_cleanup_status``) on the row. The scheduler
also aggregates a per-run breakdown so the ops dashboard can answer
"how many of yesterday's fetches were actually cleaned by DeepSeek?"
without scanning the whole ``news_article`` table.

2026-07-21: ingestion-time fetching. ``_write_to_db`` in
``scheduler_jobs`` calls :func:`fetch_full_content_for_ids` right after
persisting new rows (bounded by ``news_content_ingest_time_budget_sec``)
so the detail page usually has a body the moment an article appears.
This 10-minute job drains whatever the inline pass could not finish
(backlog, failures worth retrying, sources with their own persist path).
"""

import logging
import time
from collections.abc import Iterable

from sqlalchemy import select

from app.core.database import SessionLocal
from app.services.news._model_loader import NewsArticle

logger = logging.getLogger(__name__)

# How many articles to process per run. Raised 10 → 50 (2026-07-21):
# the local trafilatura tier has no external rate limit, so draining
# the backlog faster is cheap.
BATCH_SIZE = 50

# Maximum content length to store
MAX_CONTENT_CHARS = 10000

_ZERO_STATS = {
    "processed": 0,
    "success": 0,
    "failed": 0,
    "ai_cleaned": 0,
    "ai_skipped": 0,
    "ai_failed": 0,
}


def _fetch_batch(db, articles) -> dict[str, int]:
    """Fetch full content for ``articles``; return per-run stats."""
    from app.services.news.content_fetcher import ContentFetcher

    fetcher = ContentFetcher(db)
    stats = dict(_ZERO_STATS)
    stats["processed"] = len(articles)

    for article in articles:
        try:
            result = fetcher.fetch(article.id, force=True)
            if result.success:
                stats["success"] += 1
                logger.info(
                    f"Fetched full content for article {article.id}: " f"{article.title[:30]}"
                )
            else:
                stats["failed"] += 1
                logger.warning(f"Failed to fetch article {article.id}: {result.error}")
            # Tally the AI-cleanup outcome regardless of fetch
            # success — a "skipped" fetch is still a data point the
            # dashboard wants to see.
            status = result.ai_cleanup_status
            if status == "cleaned":
                stats["ai_cleaned"] += 1
            elif status == "skipped":
                stats["ai_skipped"] += 1
            elif status == "failed":
                stats["ai_failed"] += 1
        except Exception as e:
            stats["failed"] += 1
            logger.warning(f"Error fetching article {article.id}: {e}")

    logger.info(
        f"Full content fetch complete: {stats['success']} success, "
        f"{stats['failed']} failed (ai_cleaned={stats['ai_cleaned']}, "
        f"ai_skipped={stats['ai_skipped']}, ai_failed={stats['ai_failed']})"
    )
    return stats


def fetch_full_content_for_ids(
    article_ids: Iterable[int],
    *,
    time_budget_sec: int | None = None,
) -> dict[str, int]:
    """Fetch full content for freshly-ingested articles (ingest-time hook).

    Called by ``scheduler_jobs._write_to_db`` right after new rows are
    committed. Bounded by ``time_budget_sec`` (default:
    ``settings.news_content_ingest_time_budget_sec``) so a slow source
    page cannot stall the crawl tick; whatever is left over is drained
    by the 10-minute scheduler job.
    """
    from app.config import get_settings

    settings = get_settings()
    if not settings.news_content_fetch_on_ingest:
        return dict(_ZERO_STATS)
    if time_budget_sec is None:
        time_budget_sec = settings.news_content_ingest_time_budget_sec

    ids = list(dict.fromkeys(article_ids))  # de-dup, keep order
    if not ids or time_budget_sec <= 0:
        return dict(_ZERO_STATS)

    db = SessionLocal()
    try:
        articles = (
            db.execute(
                select(NewsArticle)
                .where(NewsArticle.id.in_(ids))
                .where(NewsArticle.full_content.is_(None))
                .where(NewsArticle.url.isnot(None))
            )
            .scalars()
            .all()
        )
        if not articles:
            return dict(_ZERO_STATS)

        deadline = time.monotonic() + time_budget_sec
        batch = []
        for article in articles:
            if batch and time.monotonic() >= deadline:
                logger.info(
                    "ingest-time content fetch: time budget exhausted, "
                    "%d article(s) left for the scheduler drain",
                    len(articles) - len(batch),
                )
                break
            batch.append(article)
        return _fetch_batch(db, batch)
    except Exception as exc:  # noqa: BLE001 - never break the crawl tick
        logger.warning("ingest-time content fetch failed: %s", exc)
        return dict(_ZERO_STATS)
    finally:
        db.close()


def run_fetch_full_content():
    """Fetch full content for articles that don't have it yet."""
    db = SessionLocal()
    try:
        # Find articles without full_content, preferring recent ones
        stmt = (
            select(NewsArticle)
            .where(NewsArticle.full_content.is_(None))
            .where(NewsArticle.url.isnot(None))
            .order_by(NewsArticle.published_at.desc())
            .limit(BATCH_SIZE)
        )
        articles = db.execute(stmt).scalars().all()

        if not articles:
            logger.info("No articles need full content fetch")
            return dict(_ZERO_STATS)

        return _fetch_batch(db, list(articles))

    finally:
        db.close()
