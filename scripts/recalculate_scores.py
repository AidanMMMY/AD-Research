#!/usr/bin/env python3
"""Recalculate ETF scores for all historical indicator dates.

After fixing scoring logic (risk dimension absolute value, market-aware
latest dates, bucket-aware rank_category), existing persisted scores must
be rewritten. This script walks every trade_date present in
``etf_indicator`` and calls ``ScoringService.calculate_daily_scores`` for
it.

Usage (inside container):
    cd /app && PYTHONPATH=/app python3 scripts/recalculate_scores.py

For a single date:
    python3 scripts/recalculate_scores.py --date 2026-07-15

Dry-run (count only):
    python3 scripts/recalculate_scores.py --dry-run
"""

import argparse
import logging
import sys
from datetime import date

from sqlalchemy import select

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("recalculate_scores")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recalculate ETF scores")
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        help="Recalculate for a single ISO date (default: all dates)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print dates/counts without writing",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of dates per progress log line",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    from app.core.database import SessionLocal
    from app.models.etf import ETFIndicator
    from app.services.scoring_service import ScoringService

    db = SessionLocal()
    try:
        if args.date:
            dates = [args.date]
        else:
            rows = db.execute(
                select(ETFIndicator.trade_date)
                .distinct()
                .order_by(ETFIndicator.trade_date.asc())
            ).all()
            dates = [r[0] for r in rows if r[0]]

        if not dates:
            logger.info("No indicator dates found; nothing to recalculate")
            return 0

        logger.info(
            "Score recalculation: %d date(s), dry_run=%s",
            len(dates),
            args.dry_run,
        )

        total_scores = 0
        for i, trade_date in enumerate(dates, 1):
            if args.dry_run:
                count = (
                    db.execute(
                        select(ETFIndicator.etf_code)
                        .where(ETFIndicator.trade_date == trade_date)
                        .distinct()
                    )
                    .scalars()
                    .all()
                )
                logger.info(
                    "[dry-run] %s: would score %d instrument(s)",
                    trade_date,
                    len(count),
                )
                continue

            service = ScoringService(db)
            results = service.calculate_daily_scores(trade_date=trade_date)
            date_total = sum(results.values())
            total_scores += date_total

            if i % args.batch_size == 0 or i == len(dates):
                logger.info(
                    "Progress %d/%d: %s -> %d scores (running total %d)",
                    i,
                    len(dates),
                    trade_date,
                    date_total,
                    total_scores,
                )

        logger.info(
            "Score recalculation finished: %d date(s), %d total score rows",
            len(dates),
            total_scores,
        )
        return 0

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
