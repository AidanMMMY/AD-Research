#!/usr/bin/env python3
"""One-shot backfill for US stock sector/category metadata.

Runs USStockEnrichmentPipeline to backfill missing sector/industry/category
for US individual stocks from the public S&P 500 CSV.  Safe to run repeatedly:
stocks that already have category are skipped.

Usage:
    docker exec alloyresearch-backend python3 app/scripts/backfill_us_stock_categories.py
    docker exec alloyresearch-backend python3 app/scripts/backfill_us_stock_categories.py --batch-size 500
"""

import argparse
import logging

from app.core.database import SessionLocal
from app.data.pipelines.us_stock_enrichment import USStockEnrichmentPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Backfill US stock sector/category from S&P 500 CSV"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Number of stocks to process per run (default 500)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        pipeline = USStockEnrichmentPipeline(db, batch_size=args.batch_size)
        result = pipeline.run()
        logger.info(
            "Backfill result: success=%s, updated=%d, error=%s, warnings=%s",
            result.success,
            result.records,
            result.error,
            result.warnings,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
