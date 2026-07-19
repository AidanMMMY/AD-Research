#!/usr/bin/env python3
"""Embed news articles for a given source.

Generates vector embeddings for ``news_article`` rows that have not yet
been embedded and persists them in ``news_article.embedding`` (JSONB).

Usage
-----
    python scripts/embed_news_articles.py --source wallstreetcn --limit 100 --batch 10

The script processes articles concurrently up to ``--concurrency`` (default 5).
Each article is committed independently so a single failure does not block
others.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import desc

from app.core.database import SessionLocal
from app.services.news._model_loader import NewsArticle
from app.services.news.rag.embedder import NewsEmbedder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


DEFAULT_BATCH = 10
DEFAULT_CONCURRENCY = 5


def _fetch_ids(db, source: str, limit: int) -> list[int]:
    """Return article IDs for the source that have not been embedded."""
    rows = (
        db.query(NewsArticle.id)
        .filter(NewsArticle.source == source)
        .filter(NewsArticle.embedded_at.is_(None))
        .order_by(desc(NewsArticle.published_at))
        .limit(limit)
        .all()
    )
    return [row.id for row in rows]


async def _embed_one(article_id: int, semaphore: asyncio.Semaphore) -> bool:
    """Embed a single article inside a fresh DB session."""
    async with semaphore:
        db = SessionLocal()
        try:
            embedder = NewsEmbedder(db)
            vector = await embedder.embed_article(article_id)
            return vector is not None
        except Exception as exc:
            logger.warning("embed article %s failed: %s", article_id, exc)
            return False
        finally:
            db.close()


async def run(source: str, limit: int, batch: int, concurrency: int) -> int:
    db = SessionLocal()
    try:
        ids = _fetch_ids(db, source, limit)
        if not ids:
            print(f"[EmbedNews] no unembedded articles for source={source}")
            return 0
        print(
            f"[EmbedNews] source={source} unembedded={len(ids)} "
            f"batch={batch} concurrency={concurrency}"
        )
    finally:
        db.close()

    semaphore = asyncio.Semaphore(concurrency)

    total_ok = 0
    total_fail = 0
    for i in range(0, len(ids), batch):
        batch_ids = ids[i : i + batch]
        results = await asyncio.gather(
            *[_embed_one(aid, semaphore) for aid in batch_ids]
        )
        ok = sum(1 for r in results if r)
        fail = len(results) - ok
        total_ok += ok
        total_fail += fail
        print(
            f"[EmbedNews] batch {i // batch + 1}: ok={ok} fail={fail} "
            f"total_ok={total_ok} total_fail={total_fail}"
        )

    print(
        f"[EmbedNews] finished source={source} ok={total_ok} fail={total_fail} "
        f"as_of={datetime.utcnow().isoformat()}"
    )
    return total_ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Embed news articles for a single source"
    )
    parser.add_argument("--source", required=True, help="news_article.source value")
    parser.add_argument(
        "--limit", type=int, default=100, help="Maximum articles to embed (default: 100)"
    )
    parser.add_argument(
        "--batch", type=int, default=DEFAULT_BATCH, help=f"Articles per batch (default: {DEFAULT_BATCH})"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Concurrent in-flight embeddings (default: {DEFAULT_CONCURRENCY})",
    )
    args = parser.parse_args()

    return asyncio.run(
        run(
            source=args.source,
            limit=args.limit,
            batch=args.batch,
            concurrency=args.concurrency,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
