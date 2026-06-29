#!/usr/bin/env python3
"""Recalculate A-share technical indicators after adj_factor backfill.

Usage (inside container):
    cd /app && PYTHONPATH=/app python3 app/scripts/recalc_a_share_indicators.py
"""

import logging
import sys

from app.core.database import SessionLocal
from app.data.indicators.calculator import batch_calculate_indicators

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("recalc_a_share_indicators")


def main() -> int:
    db = SessionLocal()
    try:
        logger.info("Starting A-share indicator recalculation")
        updated = batch_calculate_indicators(
            db,
            target_date=None,
            full_history=False,
            market_filter="A股",
        )
        logger.info("Updated %d A-share indicator records", updated)
        return 0
    except Exception as exc:
        logger.exception("A-share indicator recalculation failed: %s", exc)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
