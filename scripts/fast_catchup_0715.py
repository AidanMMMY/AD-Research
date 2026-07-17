#!/usr/bin/env python3
"""One-off single-process catch-up for A-share indicators on 2026-07-15.

Run inside the backend/celery container where app dependencies are available.
Processes active A-share codes in chunks of 20 using the SQL backend.
Safe to restart: upserts are idempotent.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import date

# Ensure app modules are importable
sys.path.insert(0, "/app")

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from app.core.database import SessionLocal
from app.data.indicators.calculator import _INDICATOR_COLUMNS
from app.data.indicators.sql_calculator import (
    build_indicator_payload,
    sql_calculate_latest,
)
from app.models.etf import ETFIndicator, ETFInfo, InstrumentDailyBar

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("fast_catchup")

TARGET_DATE = date(2026, 7, 15)
CHUNK_SIZE = int(os.environ.get("CATCHUP_CHUNK_SIZE", "20"))


def get_codes_with_bars() -> list[str]:
    db = SessionLocal()
    try:
        active_rows = db.execute(
            select(ETFInfo.code).where(
                ETFInfo.status == "active",
                ETFInfo.market == "A股",
            )
        ).all()
        active_codes = {r[0] for r in active_rows}
        codes_with_bars = {
            row[0]
            for row in db.execute(
                select(InstrumentDailyBar.etf_code).distinct().where(
                    InstrumentDailyBar.etf_code.in_(active_codes),
                    InstrumentDailyBar.trade_date <= TARGET_DATE,
                )
            )
        }
        return sorted(codes_with_bars)
    finally:
        db.close()


def main() -> int:
    codes = get_codes_with_bars()
    logger.info(
        "Single-process catch-up: total A-share codes with bars on or before %s: %d",
        TARGET_DATE,
        len(codes),
    )
    if not codes:
        return 0

    db = SessionLocal()
    updated = 0
    errors = 0
    try:
        for i in range(0, len(codes), CHUNK_SIZE):
            chunk = codes[i : i + CHUNK_SIZE]
            try:
                rows = sql_calculate_latest(db, chunk, target_date=TARGET_DATE)
                records = [build_indicator_payload(r) for r in rows]
                # Skip all-NULL rows
                records = [
                    r
                    for r in records
                    if any(r.get(c) is not None for c in _INDICATOR_COLUMNS)
                ]
                if not records:
                    continue
                insert_stmt = insert(ETFIndicator).values(records)
                upsert_stmt = insert_stmt.on_conflict_do_update(
                    index_elements=["etf_code", "trade_date"],
                    set_={col: insert_stmt.excluded[col] for col in _INDICATOR_COLUMNS},
                )
                db.execute(upsert_stmt)
                db.commit()
                updated += len(records)
                if i % (CHUNK_SIZE * 5) == 0:
                    logger.info(
                        "progress=%d/%d updated=%d errors=%d",
                        i,
                        len(codes),
                        updated,
                        errors,
                    )
            except Exception as exc:
                db.rollback()
                errors += 1
                logger.exception("chunk %d failed: %s", i, exc)
                # Sleep briefly after error to avoid hammering a struggling DB
                import time

                time.sleep(5)
    finally:
        db.close()

    logger.info("Done. updated=%d errors=%d", updated, errors)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
