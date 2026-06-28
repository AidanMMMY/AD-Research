#!/usr/bin/env python3
"""One-time initialization script for A-share individual stocks.

Steps:
  1. Discovery: Fetch and register all A-share stocks via Tushare stock_basic.
  2. Daily bars: Fetch historical daily bars for the current week.
  3. Fundamentals: Fetch daily_basic (PE, PB, market cap) for latest trading day.

Usage:
    python app/scripts/init_a_share_stocks.py              # Full init
    python app/scripts/init_a_share_stocks.py --discovery  # Discovery only
    python app/scripts/init_a_share_stocks.py --daily      # Daily bars only
    python app/scripts/init_a_share_stocks.py --fundamental # Fundamentals only
    python app/scripts/init_a_share_stocks.py --date 20260626  # Target date

After running this script once, the scheduler will maintain data freshness
(see app/core/scheduler.py for cron schedules).
"""

import argparse
import sys
from datetime import date, timedelta


def parse_date(value: str | None) -> date | None:
    """Parse YYYYMMDD string to date, or return None."""
    if value is None:
        return None
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except (ValueError, IndexError):
        print(f"Error: Invalid date format '{value}'. Use YYYYMMDD (e.g., 20260626).")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Initialize A-share individual stock data"
    )
    parser.add_argument(
        "--discovery", action="store_true",
        help="Run stock discovery pipeline only",
    )
    parser.add_argument(
        "--daily", action="store_true",
        help="Run daily bars pipeline only",
    )
    parser.add_argument(
        "--fundamental", action="store_true",
        help="Run fundamental/valuation pipeline only",
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="Target trade date in YYYYMMDD format (default: yesterday)",
    )
    parser.add_argument(
        "--financials", action="store_true",
        help="Run financial statements pipeline (batch of 50 stocks, rotating)",
    )
    args = parser.parse_args()

    # Default: run all
    run_all = not (args.discovery or args.daily or args.fundamental or args.financials)

    target_date = parse_date(args.date)

    from app.core.database import SessionLocal

    # ── Discovery ──────────────────────────────────────────────
    if run_all or args.discovery:
        print("=" * 60)
        print("[init_a_share_stocks] Running stock discovery...")
        from app.data.pipelines.a_share_stock_discovery import AShareStockDiscoveryPipeline

        db = SessionLocal()
        try:
            pipeline = AShareStockDiscoveryPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(f"  success={result.success}, records={result.records}")
            if result.error:
                print(f"  ERROR: {result.error}")
        finally:
            db.close()
        print()

    # ── Daily ETL ──────────────────────────────────────────────
    if run_all or args.daily:
        print("=" * 60)
        print(f"[init_a_share_stocks] Running daily bars ETL (target={target_date})...")
        from app.data.pipelines.a_share_stock_daily import AStockDailyPipeline

        db = SessionLocal()
        try:
            pipeline = AStockDailyPipeline(db, target_date=target_date)
            result = pipeline.run_with_retry(max_attempts=2)
            print(f"  success={result.success}, records={result.records}")
            if result.error:
                print(f"  ERROR: {result.error}")
        finally:
            db.close()
        print()

    # ── Fundamental / Valuation ────────────────────────────────
    if run_all or args.fundamental:
        print("=" * 60)
        print(f"[init_a_share_stocks] Running fundamental ETL (target={target_date})...")
        from app.data.pipelines.a_share_stock_fundamental import AStockFundamentalPipeline

        db = SessionLocal()
        try:
            pipeline = AStockFundamentalPipeline(db, target_date=target_date)
            result = pipeline.run()
            print(f"  success={result.success}, records={result.records}")
            if result.error:
                print(f"  ERROR: {result.error}")
        finally:
            db.close()
        print()

    # ── Financial Statements ───────────────────────────────────
    if args.financials:
        print("=" * 60)
        print("[init_a_share_stocks] Running financial statements ETL...")
        from app.data.pipelines.a_share_stock_financials import AStockFinancialsPipeline

        db = SessionLocal()
        try:
            pipeline = AStockFinancialsPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(f"  success={result.success}, records={result.records}")
            if result.error:
                print(f"  ERROR: {result.error}")
        finally:
            db.close()
        print()

    print("=" * 60)
    print("[init_a_share_stocks] Done!")


if __name__ == "__main__":
    main()
