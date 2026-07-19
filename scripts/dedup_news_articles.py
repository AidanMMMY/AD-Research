#!/usr/bin/env python3
"""Near-duplicate detection for news articles using simhash.

Finds article pairs whose 64-bit content hashes are within a Hamming
distance threshold.  By default the script is dry-run and only prints the
pairs it would merge.  Pass ``--merge`` to write the ``duplicate_of``
foreign key on the newer article of each pair.

Usage
-----
    python scripts/dedup_news_articles.py --threshold 3 --days 7
    python scripts/dedup_news_articles.py --source wallstreetcn --source 36kr --threshold 3 --merge
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.services.news.dedup import find_near_duplicates, mark_duplicates

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Find near-duplicate news articles using simhash"
    )
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        metavar="SOURCE",
        help="Restrict to one or more sources (repeatable; default: all)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=3,
        help="Max Hamming distance to consider a duplicate (default: 3)",
    )
    parser.add_argument(
        "--days", type=int, default=7, help="Look-back window in days (default: 7)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5000,
        help="Maximum articles to load into memory (default: 5000)",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        default=False,
        help="Write duplicate_of on newer articles (default: dry-run)",
    )
    args = parser.parse_args()

    sources = args.sources or None
    print(
        f"[DedupNews] sources={sources or 'all'} threshold={args.threshold} "
        f"days={args.days} limit={args.limit} merge={args.merge}"
    )

    db = SessionLocal()
    try:
        pairs = find_near_duplicates(
            db=db,
            threshold_bits=args.threshold,
            sources=sources,
            limit=args.limit,
            days=args.days,
        )
        print(f"[DedupNews] found {len(pairs)} near-duplicate pair(s)")
        for aid, bid, distance in pairs:
            print(f"  article {aid} <-> article {bid}  distance={distance}")

        if not pairs:
            return 0

        if not args.merge:
            print("[DedupNews] dry-run; pass --merge to update duplicate_of")
            return 0

        updated = mark_duplicates(db, pairs)
        print(f"[DedupNews] updated {updated} row(s) with duplicate_of")
        return 0
    except Exception as exc:
        logger.exception("dedup failed: %s", exc)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
