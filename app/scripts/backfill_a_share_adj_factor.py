#!/usr/bin/env python3
"""Backfill adj_factor for existing A-share daily bars.

Fetches Tushare ``adj_factor()`` per stock over the full date range where
local bars exist, then bulk-updates ``instrument_daily_bar.adj_factor``.

Usage (inside container):
    cd /app && PYTHONPATH=/app python3 app/scripts/backfill_a_share_adj_factor.py
"""

import logging
import sys
import time
from datetime import date

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
        # Active A-share stocks + local bar date range
        meta_sql = text(
            """
            SELECT
                e.code,
                COALESCE(MIN(b.trade_date), CURRENT_DATE) AS min_date,
                COALESCE(MAX(b.trade_date), CURRENT_DATE) AS max_date
            FROM etf_info e
            LEFT JOIN instrument_daily_bar b ON b.etf_code = e.code
            WHERE e.market = 'A股'
              AND e.instrument_type = 'STOCK'
              AND e.status = 'active'
            GROUP BY e.code
            ORDER BY e.code
            """
        )
        stocks = [
            {"code": row[0], "min_date": row[1], "max_date": row[2]}
            for row in db.execute(meta_sql)
        ]
        logger.info("Found %d active A-share stocks", len(stocks))
        if not stocks:
            return 0

        records: list[tuple[str, date, float]] = []
        errors: list[str] = []

        for i, stock in enumerate(stocks):
            code = stock["code"]
            start_date = stock["min_date"]
            end_date = stock["max_date"]
            label = f"[{i + 1}/{len(stocks)}] {code}"
            print(f"  {label} ...", end=" ", flush=True)

            if start_date > end_date:
                print("no local bars")
                continue

            try:
                df = provider.fetch_adj_factor(
                    ts_code=code, start_date=start_date, end_date=end_date
                )
            except Exception as exc:
                msg = f"API error: {exc}"
                print(f"FAILED — {msg}")
                errors.append(f"{code}: {msg}")
                continue

            if df is None or df.empty:
                print("no data")
                continue

            added = 0
            for _, row in df.iterrows():
                trade_date = row.get("trade_date")
                af = row.get("adj_factor")
                if trade_date and pd.notna(af):
                    records.append((code, trade_date, float(af)))
                    added += 1

            print(f"OK ({added} rows)")

        if not records:
            logger.warning("No adj_factor records fetched")
            return 0

        # Bulk update in chunks via VALUES ... FROM
        updated = 0
        chunk_size = 5000
        for chunk in _chunked(records, chunk_size):
            values = ", ".join(
                f"('{code}', '{td.isoformat()}', {af})"
                for code, td, af in chunk
            )
            update_sql = text(
                f"""
                UPDATE instrument_daily_bar AS t
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
            "Updated %d / %d instrument_daily_bar rows (fetched %d adj_factor records)",
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
