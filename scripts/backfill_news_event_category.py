#!/usr/bin/env python3
"""Backfill missing ``news_article.event_category`` via the LLM pipeline.

Iterates over ``news_article`` rows where ``event_category IS NULL`` and
re-runs the entity-extraction stage of the sentiment pipeline. The
extracted ``event_category`` is written back to ``news_article`` by
``SentimentPipeline._backfill_article_sentiment``; this script also
commits the per-symbol ``sentiment_data`` rows produced by the pipeline.

Concurrency is bounded by ``process_batch(..., concurrency=10)``; the
pipeline has its own semaphore for in-flight LLM calls.

Usage
-----
    # Dry-run: print how many rows would be processed, no writes
    python scripts/backfill_news_event_category.py

    # Live run (must omit --dry-run or pass --no-dry-run)
    python scripts/backfill_news_event_category.py --no-dry-run

    # Limit total articles processed
    python scripts/backfill_news_event_category.py --no-dry-run --limit 500

    # Tune batch size (default 50)
    python scripts/backfill_news_event_category.py --no-dry-run --batch-size 100
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.core.database import SessionLocal
from app.services.news.sentiment import SentimentPipeline
from app.services.news._model_loader import NewsArticle

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


DEFAULT_BATCH_SIZE = 50
DEFAULT_CONCURRENCY = 10


def _build_article_dict(row: NewsArticle) -> dict:
    """Construct the minimal article dict the pipeline expects."""
    return {
        "id": row.id,
        "url": row.url or f"news:{row.id}",
        "title": row.title or "",
        "body": (
            row.full_content
            or row.body
            or row.body_html
            or row.summary
            or ""
        ),
        "published_at": row.published_at,
    }


def _fetch_null_batch(db, limit: int, offset: int) -> list[NewsArticle]:
    """Return the next batch of rows needing event_category."""
    return (
        db.query(NewsArticle)
        .filter(NewsArticle.event_category.is_(None))
        .order_by(NewsArticle.published_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )


def _count_null(db) -> int:
    """Count rows with event_category IS NULL."""
    # Use text() for a portable COUNT on the NULL condition.
    result = db.execute(
        text(
            """
            SELECT COUNT(*) AS n
            FROM news_article
            WHERE event_category IS NULL
            """
        )
    ).mappings().first()
    return int(result["n"]) if result else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill news_article.event_category using the sentiment pipeline"
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Print counts without writing (default: true)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum total articles to process (default: unlimited)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Articles per batch (default: {DEFAULT_BATCH_SIZE})",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        total_null = _count_null(db)
        print("=" * 70)
        print("Backfill news_article.event_category")
        print(f"  mode       : {'DRY-RUN' if args.dry_run else 'COMMIT'}")
        print(f"  limit      : {args.limit if args.limit is not None else 'unlimited'}")
        print(f"  batch size : {args.batch_size}")
        print(f"  rows NULL  : {total_null:,}")
        print("=" * 70)

        if total_null == 0:
            print("\n[OK] No rows need backfill.")
            return 0

        if args.dry_run:
            print("\n[DRY-RUN] Would process up to "
                  f"{args.limit if args.limit is not None else total_null:,} rows.")
            return 0

        pipeline = SentimentPipeline(db)
        processed = 0
        updated = 0
        failed = 0
        offset = 0
        remaining_limit = args.limit

        while True:
            batch_limit = args.batch_size
            if remaining_limit is not None:
                batch_limit = min(args.batch_size, remaining_limit)

            rows = _fetch_null_batch(db, batch_limit, offset)
            if not rows:
                break

            articles = [_build_article_dict(r) for r in rows]
            results = asyncio.run(
                pipeline.process_batch(articles, concurrency=DEFAULT_CONCURRENCY)
            )

            batch_updated = 0
            batch_failed = 0
            for row, res in zip(rows, results):
                if res.success:
                    batch_updated += 1
                else:
                    batch_failed += 1
                    logger.warning(
                        "Pipeline failed for article id=%s: %s",
                        row.id, res.error or "unknown error",
                    )

            # Commit per batch so partial progress is preserved.
            try:
                db.commit()
            except Exception as exc:
                logger.exception("Batch commit failed, rolling back")
                db.rollback()
                failed += len(rows)
                offset += len(rows)
                if remaining_limit is not None:
                    remaining_limit -= len(rows)
                continue

            processed += len(rows)
            updated += batch_updated
            failed += batch_failed
            offset += len(rows)
            if remaining_limit is not None:
                remaining_limit -= len(rows)

            logger.info(
                "Batch committed: processed=%d updated=%d failed=%d",
                processed, updated, failed,
            )

            if remaining_limit is not None and remaining_limit <= 0:
                break

        print("\n" + "=" * 70)
        print("Backfill complete")
        print(f"  processed : {processed:,}")
        print(f"  updated   : {updated:,}")
        print(f"  failed    : {failed:,}")
        print("=" * 70)
        return 0 if failed == 0 else 1

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
