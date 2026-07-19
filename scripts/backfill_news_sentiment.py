#!/usr/bin/env python3
"""Backfill sentiment for selected Chinese news sources.

Runs the same LLM sentiment pipeline as the scheduled
``run_source_sentiment_backfill`` task, but from the command line so
ops can catch up newly added sources without waiting for the next
scheduled tick.

Usage
-----
    python scripts/backfill_news_sentiment.py --source wallstreetcn --limit 200
    python scripts/backfill_news_sentiment.py --source wallstreetcn --source 36kr --limit 500
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.news.sentiment.scheduler_sentiment import (
    _CHINESE_BACKFILL_SOURCES,
    run_source_sentiment_backfill,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill sentiment for news_article rows from selected sources"
    )
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        metavar="SOURCE",
        help="Source to backfill (repeatable). Defaults to all Chinese sources.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum rows to process per run (default: 500)",
    )
    args = parser.parse_args()

    sources = args.sources or _CHINESE_BACKFILL_SOURCES
    print(f"[BackfillSentiment] sources={sources} limit={args.limit}")
    ok = run_source_sentiment_backfill(sources=sources, limit=args.limit)
    print(f"[BackfillSentiment] success={ok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
