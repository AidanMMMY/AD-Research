"""Scheduled job to fetch full content for news articles.

Runs after the Xueqiu crawler to fetch and clean article content
using Jina Reader + AI.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, func

from app.core.database import SessionLocal
from app.models.news import NewsArticle

logger = logging.getLogger(__name__)

# How many articles to process per run
BATCH_SIZE = 10

# Maximum content length to store
MAX_CONTENT_CHARS = 10000


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
            return {"processed": 0, "success": 0, "failed": 0}

        from app.services.news.content_fetcher import ContentFetcher

        fetcher = ContentFetcher(db)
        success = 0
        failed = 0

        for article in articles:
            try:
                result = fetcher.fetch(article.id, force=True)
                if result.success:
                    success += 1
                    logger.info(f"Fetched full content for article {article.id}: {article.title[:30]}")
                else:
                    failed += 1
                    logger.warning(f"Failed to fetch article {article.id}: {result.error}")
            except Exception as e:
                failed += 1
                logger.warning(f"Error fetching article {article.id}: {e}")

        logger.info(f"Full content fetch complete: {success} success, {failed} failed")
        return {"processed": len(articles), "success": success, "failed": failed}

    finally:
        db.close()
