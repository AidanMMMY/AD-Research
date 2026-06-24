#!/usr/bin/env python3
"""Seed US ETF instruments into the etf_info table.

Uses FinnhubProvider's curated list (~70 highly liquid US ETFs)
as the primary source. Falls back to yfinance for basic info.

Usage:
    python scripts/init_us_etfs.py          # dry-run (print what would be inserted)
    python scripts/init_us_etfs.py --apply   # actually insert into DB
"""

import argparse
import os
import sys

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date

from app.core.database import SessionLocal
from app.data.providers.finnhub_provider import FinnhubProvider
from app.models.etf import ETFInfo


def main(apply: bool = False):
    db = SessionLocal()
    provider = FinnhubProvider()

    try:
        etf_list = provider.fetch_etf_list()
    except Exception as exc:
        print(f"Finnhub ETF list failed: {exc}")
        print("Ensure FINNHUB_API_KEY is set in .env")
        sys.exit(1)

    if not etf_list:
        print("No ETFs returned from FinnhubProvider. Aborting.")
        sys.exit(1)

    print(f"Found {len(etf_list)} US ETFs")
    print()

    inserted = 0
    skipped = 0
    for info in etf_list:
        # Check if already exists
        existing = db.query(ETFInfo).filter(ETFInfo.code == info.code).first()
        if existing:
            print(f"  SKIP  {info.code:12s} already exists: {existing.name}")
            skipped += 1
            continue

        if apply:
            record = ETFInfo(
                code=info.code,
                name=info.name,
                exchange=info.exchange,
                market=info.market or "US",
                category=info.category,
                currency=info.currency or "USD",
                instrument_type="ETF",
                country="US",
                status="active",
            )
            db.add(record)

        print(f"  {'ADD' if apply else 'DRYRUN'} {info.code:12s} | {info.name:50s} | {info.category or '-':10s} | {info.exchange or '-':8s}")
        inserted += 1

    if apply:
        db.commit()
        print()
        print(f"Committed {inserted} new US ETF records to DB (skipped {skipped} existing)")
    else:
        print()
        print(f"Dry run: would insert {inserted} records (skipped {skipped} existing)")
        print("Run with --apply to actually insert")

    db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed US ETF instruments")
    parser.add_argument("--apply", action="store_true", help="Actually insert into DB")
    args = parser.parse_args()
    main(apply=args.apply)
