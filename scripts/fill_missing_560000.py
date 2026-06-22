#!/usr/bin/env python3
"""Fill missing daily bars for 560000.SH with synthetic demo data.

This ETF's data source stops at 2026-04-30. To keep the platform dataset
complete and consistent, we generate synthetic bars from 2026-05-01 to the
latest available trading date, derived from the last real close price with
small random drift.
"""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.core.calendar import get_trading_dates
from app.models.etf import ETFDailyBar

settings = get_settings()
engine = create_engine(settings.database_url)

TARGET_CODE = "560000.SH"


def get_last_real_bar() -> dict:
    with engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT trade_date, close
            FROM etf_daily_bar
            WHERE etf_code = '{TARGET_CODE}' AND (is_synthetic IS NULL OR is_synthetic = false)
            ORDER BY trade_date DESC
            LIMIT 1
        """)).fetchone()
        return {"trade_date": result[0], "close": float(result[1])} if result else None


def generate_synthetic_bars(last_close: float, trade_dates: list[date]) -> list[dict]:
    records = []
    close = last_close
    for trade_date in trade_dates:
        # Small random daily drift (-1% to +1%)
        drift = (hash(trade_date.isoformat()) % 200 - 100) / 10000
        close = close * (1 + drift)
        open_price = close * (1 + (hash(trade_date.isoformat() + "open") % 100 - 50) / 10000)
        high = max(open_price, close) * (1 + abs(hash(trade_date.isoformat() + "high") % 50) / 10000)
        low = min(open_price, close) * (1 - abs(hash(trade_date.isoformat() + "low") % 50) / 10000)
        volume = 100000 + abs(hash(trade_date.isoformat() + "vol") % 900000)
        amount = volume * close
        change_pct = (close - (close / (1 + drift))) / (close / (1 + drift)) * 100

        records.append({
            "etf_code": TARGET_CODE,
            "trade_date": trade_date,
            "open": round(open_price, 4),
            "high": round(high, 4),
            "low": round(low, 4),
            "close": round(close, 4),
            "volume": int(volume),
            "amount": round(amount, 4),
            "pre_close": round(close / (1 + drift), 4),
            "change_pct": round(change_pct, 4),
            "turnover_rate": round(0.5 + abs(hash(trade_date.isoformat() + "turn") % 400) / 100, 4),
            "is_synthetic": True,
        })
    return records


def upsert_bars(records: list[dict]) -> int:
    if not records:
        return 0
    insert_stmt = insert(ETFDailyBar).values(records)
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=["etf_code", "trade_date"],
        set_={
            col: insert_stmt.excluded[col]
            for col in [
                "open", "high", "low", "close", "volume", "amount",
                "pre_close", "change_pct", "turnover_rate", "is_synthetic",
            ]
        },
    )
    with engine.begin() as conn:
        result = conn.execute(upsert_stmt)
        return result.rowcount


def main():
    print(f"=== Filling missing bars for {TARGET_CODE} ===")
    last = get_last_real_bar()
    if not last:
        print("No real bar found, skipping.")
        return
    print(f"Last real bar: {last['trade_date']} @ {last['close']}")

    with engine.connect() as conn:
        latest = conn.execute(text("SELECT MAX(trade_date) FROM etf_daily_bar")).scalar()

    trade_dates = get_trading_dates(last["trade_date"] + timedelta(days=1), latest)
    print(f"Generating {len(trade_dates)} synthetic bars up to {latest}")

    records = generate_synthetic_bars(last["close"], trade_dates)
    count = upsert_bars(records)
    print(f"Upserted {count} synthetic daily bar records.")


if __name__ == "__main__":
    main()
