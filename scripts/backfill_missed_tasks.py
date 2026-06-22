#!/usr/bin/env python3
"""Backfill missed scheduled tasks from 2026-06-13 to 2026-06-18.

Optimized version: uses Sina interface to fetch full history once per ETF,
then filters multiple trade dates in-memory, reducing API calls by ~6x.
"""

import math
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.calendar import get_trading_dates
from app.core.database import SessionLocal
from app.core.scheduler import (
    run_etf_scan,
    run_indicator_calculation,
    run_score_calculation,
    run_signal_generation,
    run_weekly_pool_reports,
)
from app.data.providers.akshare_provider import AkshareProvider
from app.models.etf import ETFDailyBar, ETFInfo


def backfill_daily_bars(target_dates: list[date]):
    """Fetch and upsert daily bars for target dates using Sina (stable)."""
    db = SessionLocal()
    try:
        # Query active A-share ETFs
        etfs = (
            db.execute(
                select(ETFInfo.code).where(
                    ETFInfo.status == "active",
                    ETFInfo.market == "A股",
                )
            )
            .scalars()
            .all()
        )
        print(f"[ETL Backfill] {len(etfs)} active ETFs, target dates: {target_dates}")

        provider = AkshareProvider(prefer_sina=True)
        target_dates_set = set(target_dates)
        all_records = []

        for idx, code in enumerate(etfs, 1):
            try:
                start = min(target_dates) - timedelta(days=7)
                end = max(target_dates)
                df = provider.fetch_daily_bars([code], start, end)
                if df.empty:
                    continue

                df = df[df["trade_date"].isin(target_dates_set)].copy()
                if df.empty:
                    continue

                def _clean_value(v):
                    if v is None:
                        return None
                    if isinstance(v, float) and math.isnan(v):
                        return None
                    if v is pd.NA:
                        return None
                    return v

                for _, row in df.iterrows():
                    record = {
                        "etf_code": _clean_value(row.get("etf_code")),
                        "trade_date": _clean_value(row.get("trade_date")),
                        "open": _clean_value(row.get("open")),
                        "high": _clean_value(row.get("high")),
                        "low": _clean_value(row.get("low")),
                        "close": _clean_value(row.get("close")),
                        "volume": _clean_value(row.get("volume")),
                        "amount": _clean_value(row.get("amount")),
                        "pre_close": _clean_value(row.get("pre_close")),
                        "change_pct": _clean_value(row.get("change_pct")),
                        "turnover_rate": _clean_value(row.get("turnover_rate")),
                    }
                    record = {k: v for k, v in record.items() if v is not None}
                    all_records.append(record)

                if idx % 100 == 0:
                    print(f"  -> processed {idx}/{len(etfs)} ETFs, records so far: {len(all_records)}")
            except Exception as exc:
                print(f"  -> failed {code}: {exc}")
                continue

        if not all_records:
            print("[ETL Backfill] No records to insert")
            return 0

        # Bulk upsert
        stmt = (
            insert(ETFDailyBar)
            .values(all_records)
            .on_conflict_do_update(
                index_elements=["etf_code", "trade_date"],
                set_={
                    "open": insert(ETFDailyBar).excluded.open,
                    "high": insert(ETFDailyBar).excluded.high,
                    "low": insert(ETFDailyBar).excluded.low,
                    "close": insert(ETFDailyBar).excluded.close,
                    "volume": insert(ETFDailyBar).excluded.volume,
                    "amount": insert(ETFDailyBar).excluded.amount,
                    "pre_close": insert(ETFDailyBar).excluded.pre_close,
                    "change_pct": insert(ETFDailyBar).excluded.change_pct,
                    "turnover_rate": insert(ETFDailyBar).excluded.turnover_rate,
                },
            )
        )
        db.execute(stmt)
        db.commit()
        print(f"[ETL Backfill] Upserted {len(all_records)} daily bar records")
        return len(all_records)
    finally:
        db.close()


def main():
    today = date.today()
    print(f"=== 开始补跑错过时间的定时任务 (today={today}) ===\n")

    # 1. ETL: fetch daily bars for 2026-06-13 .. 2026-06-18
    etl_dates = get_trading_dates(date(2026, 6, 13), date(2026, 6, 18))
    print(f"[1/6] ETL 补跑: {min(etl_dates)} ~ {max(etl_dates)} (优先使用新浪接口，每只 ETF 只请求一次)")
    backfill_daily_bars(etl_dates)
    print()

    # 2. Indicator calculation: full_history once up to 2026-06-18
    ind_end = max(etl_dates)
    print(f"[2/6] 指标计算补跑: 截至 {ind_end} (full_history=True)")
    run_indicator_calculation(target_date=ind_end, full_history=True)
    print()

    # 3. Score calculation: for each trading date in the backfill window
    score_dates = get_trading_dates(date(2026, 6, 11), date(2026, 6, 18))
    print(f"[3/6] 评分计算补跑: {min(score_dates)} ~ {max(score_dates)}")
    for d in score_dates:
        print(f"  -> 计算 {d} 评分")
        run_score_calculation(target_date=d)
    print()

    # 4. Signal generation: for each trading date in the backfill window
    signal_dates = get_trading_dates(date(2026, 6, 13), date(2026, 6, 18))
    print(f"[4/6] 信号生成补跑: {min(signal_dates)} ~ {max(signal_dates)}")
    for d in signal_dates:
        print(f"  -> 生成 {d} 信号")
        run_signal_generation(target_date=d)
    print()

    # 5. ETF market scan (run once for current date)
    print("[5/6] 全市场 ETF 扫描")
    run_etf_scan()
    print()

    # 6. Weekly pool reports (run once for current date)
    print("[6/6] 池周报生成")
    run_weekly_pool_reports()
    print()

    print("=== 补跑完成 ===")


if __name__ == "__main__":
    main()
