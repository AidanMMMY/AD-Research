#!/usr/bin/env python3
"""Seed demo FX rates for cross-border ETF analysis.

Since live FX data for 2026 is not available, this script generates
realistic synthetic daily FX rates (USD/CNY, HKD/CNY, JPY/CNY, EUR/CNY)
for every trading day present in instrument_daily_bar.
"""

import os
import sys
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.models.etf import FXRate

settings = get_settings()
engine = create_engine(settings.database_url)


# Base rates (roughly realistic as of recent years)
BASE_RATES = {
    ("USD", "CNY"): 7.20,
    ("HKD", "CNY"): 0.92,
    ("JPY", "CNY"): 0.046,
    ("EUR", "CNY"): 7.80,
}


def get_trading_dates() -> list[date]:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT DISTINCT trade_date FROM instrument_daily_bar ORDER BY trade_date"))
        return [row[0] for row in result]


def generate_rates(trading_dates: list[date]) -> list[dict]:
    records = []
    rng = pd.date_range(start=min(trading_dates), end=max(trading_dates), freq="B")
    business_days = {d.date() for d in rng}

    for trade_date in trading_dates:
        if trade_date not in business_days:
            continue
        day_index = (trade_date - min(trading_dates)).days
        for (from_currency, to_currency), base in BASE_RATES.items():
            # Add small random-looking drift based on day index
            drift = 0.002 * (day_index % 60 - 30) / 30
            rate = base * (1 + drift)
            records.append({
                "from_currency": from_currency,
                "to_currency": to_currency,
                "trade_date": trade_date,
                "rate": round(rate, 8),
                "source": "demo",
            })
    return records


def upsert_rates(records: list[dict]) -> int:
    if not records:
        return 0
    insert_stmt = insert(FXRate).values(records)
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=["from_currency", "to_currency", "trade_date"],
        set_={
            "rate": insert_stmt.excluded.rate,
            "source": insert_stmt.excluded.source,
        },
    )
    with engine.begin() as conn:
        result = conn.execute(upsert_stmt)
        return result.rowcount


def main():
    print("=== Seeding demo FX rates ===")
    trading_dates = get_trading_dates()
    print(f"Found {len(trading_dates)} distinct trading dates.")
    records = generate_rates(trading_dates)
    count = upsert_rates(records)
    print(f"Upserted {count} FX rate records.")


if __name__ == "__main__":
    main()
