#!/usr/bin/env python3
"""Clean up anomalous daily bar records.

Zero or negative volume is likely a data quality issue (or represents an
illiquid/suspended day). We keep the price intact but set volume to 0 so
that downstream aggregations and numeric calculations behave predictably.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.core.database import SessionLocal


def main():
    db = SessionLocal()
    try:
        print("=== Cleaning daily bar anomalies ===")
        result = db.execute(text("""
            UPDATE etf_daily_bar
            SET volume = 0
            WHERE volume <= 0
            RETURNING etf_code, trade_date, close
        """))
        rows = result.fetchall()
        db.commit()
        print(f"Cleaned {len(rows)} records (volume <= 0 set to 0):")
        for row in rows:
            print(f"  {row}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
