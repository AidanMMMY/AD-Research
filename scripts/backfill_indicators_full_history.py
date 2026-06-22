#!/usr/bin/env python3
"""Backfill etf_indicator for all historical daily bars.

Calculates indicators for every (etf_code, trade_date) that has a daily bar
but no indicator record, using the full_history mode of the batch calculator.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.data.indicators.calculator import batch_calculate_indicators


def main():
    db = SessionLocal()
    try:
        print("=== Backfilling indicators for full history ===")
        count = batch_calculate_indicators(db, full_history=True)
        print(f"Upserted {count} indicator records.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
