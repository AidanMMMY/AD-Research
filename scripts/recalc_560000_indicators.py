#!/usr/bin/env python3
"""Recalculate indicators for 560000.SH after synthetic bar backfill."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.database import SessionLocal
from app.data.indicators.calculator import (
    _INDICATOR_COLUMNS,
    _build_indicator_record,
    calculate_single_etf,
)
from app.models.etf import InstrumentDailyBar, ETFIndicator

TARGET_CODE = "560000.SH"


def main():
    db = SessionLocal()
    try:
        bars = db.execute(
            select(InstrumentDailyBar).where(InstrumentDailyBar.etf_code == TARGET_CODE).order_by(InstrumentDailyBar.trade_date.asc())
        ).scalars().all()

        if len(bars) < 5:
            print(f"Not enough bars for {TARGET_CODE}")
            return

        df = pd.DataFrame([
            {
                "trade_date": b.trade_date,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bars
        ])

        result_df = calculate_single_etf(TARGET_CODE, df)
        records = [_build_indicator_record(TARGET_CODE, row) for _, row in result_df.iterrows()]

        for record in records:
            upsert_stmt = (
                insert(ETFIndicator)
                .values(record)
                .on_conflict_do_update(
                    index_elements=["etf_code", "trade_date"],
                    set_={col: record[col] for col in _INDICATOR_COLUMNS if col in record},
                )
            )
            db.execute(upsert_stmt)
        db.commit()
        print(f"Upserted {len(records)} indicator records for {TARGET_CODE}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
