#!/usr/bin/env python3
"""Backfill adj_factor for existing A-share daily bars.

Fetches Tushare adj_factor() market-wide by trade_date and updates
etf_daily_bar.adj_factor for all A-share stocks.  Runs one API call per
distinct trade_date present in the local bars table.

Usage (inside container):
    cd /app && PYTHONPATH=/app python3 app/scripts/backfill_a_share_adj_factor.py
"""

import logging
import sys
import time
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_a_share_adj_factor")


def _chunked(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def main() -> int:
    from app.core.database import SessionLocal
    from app.data.providers.tushare_provider import TushareProvider

    provider = TushareProvider()
    db = SessionLocal()

    try:
        # Distinct trade dates for A-share stocks
        dates_sql = text(
            """
            SELECT DISTINCT trade_date
            FROM etf_daily_bar
            WHERE etf_code IN (
                SELECT code FROM etf_info
                WHERE market = 'A股' AND instrument_type = 'STOCK' AND status = 'active'
            )
            ORDER BY trade_date
            """
        )
        trade_dates = [r[0] for r in db.execute(dates_sql)]
        logger.info("Found %d distinct A-share trade dates", len(trade_dates))
        if not trade_dates:
            return 0

        records: list[tuple[str, date, float]] = []
        errors: list[str] = []

        for i, td in enumerate(trade_dates):
            label = f"[{i + 1}/{len(trade_dates)}] {td}"
            print(f"  {label} ...", end=" ", flush=True)
            try:
                df = provider.fetch_adj_factor(trade_date=td)
            except Exception as exc:
                msg = f"API error: {exc}"
                print(f"FAILED — {msg}")
                errors.append(f"{td}: {msg}")
                time.sleep(0.5)
                continue

            if df is None or df.empty:
                print("no data")
                time.sleep(0.5)
                continue

            for _, row in df.iterrows():
                code = row.get("etf_code")
                af = row.get("adj_factor")
                if code and pd.notna(af):
                    records.append((code, td, float(af)))

            print(f"OK ({len(df)} rows)")
            time.sleep(0.5)

        if not records:
            logger.warning("No adj_factor records fetched")
            return 0

        # Bulk update in chunks via VALUES ... FROM
        updated = 0
        chunk_size = 2000
        for chunk in _chunked(records, chunk_size):
            values = ", ".join(
                f"('{code}', '{td.isoformat()}', {af})"
                for code, td, af in chunk
            )
            update_sql = text(
                f"""
                UPDATE etf_daily_bar AS t
                SET adj_factor = v.adj_factor
                FROM (VALUES {values}) AS v(etf_code, trade_date, adj_factor)
                WHERE t.etf_code = v.etf_code
                  AND t.trade_date = v.trade_date::date
                """
            )
            try:
                result = db.execute(update_sql)
                db.commit()
                updated += result.rowcount
            except Exception as exc:
                db.rollback()
                logger.error("Bulk update failed: %s", exc)
                errors.append(f"bulk update: {exc}")

        logger.info(
            "Updated %d / %d etf_daily_bar rows (fetched %d adj_factor records)",
            updated, len(records), len(records),
        )
        if errors:
            logger.warning("Errors: %d", len(errors))
            for e in errors[:10]:
                logger.warning("  %s", e)

        return 0 if not errors else 1

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
