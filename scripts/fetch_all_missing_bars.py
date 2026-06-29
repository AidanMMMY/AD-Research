"""为全部ETF补采缺失的日K数据.

获取所有ETF从最新日期到2026-06-08的缺失日K数据.
"""

import os
import sys
import time
import warnings
from datetime import date, timedelta

import pandas as pd

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.data.providers.akshare_provider import AkshareProvider
from app.models.etf import InstrumentDailyBar

settings = get_settings()
engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)

TARGET_DATE = date(2026, 6, 8)


def get_etf_latest_dates(db):
    """Get latest trade_date for each ETF."""
    result = db.execute(text('''
        SELECT etf_code, MAX(trade_date) as max_date
        FROM instrument_daily_bar
        GROUP BY etf_code
        ORDER BY max_date DESC
    ''')).fetchall()
    return {r[0]: r[1] for r in result}


def main():
    db = Session()
    try:
        print("=" * 60)
        print("📊 全量ETF日K数据补采")
        print("=" * 60)

        # Get all ETFs and their latest dates
        latest_dates = get_etf_latest_dates(db)
        print(f"\n总ETF数: {len(latest_dates)}")

        # Find ETFs needing update
        need_update = {
            code: latest
            for code, latest in latest_dates.items()
            if latest < TARGET_DATE
        }

        print(f"需要补采的ETF: {len(need_update)} 只")
        if not need_update:
            print("✅ 所有ETF数据已是最新")
            return

        # Show date distribution
        from collections import Counter
        date_counts = Counter(need_update.values())
        print("\n缺失数据分布:")
        for d, c in sorted(date_counts.items(), reverse=True):
            print(f"  最新到 {d}: {c} 只")

        # Determine global fetch window. Use a small buffer before the earliest
        # missing start so that the provider can cover holidays/weekends.
        fetch_starts = {
            code: latest + timedelta(days=1)
            for code, latest in need_update.items()
        }
        global_start = min(fetch_starts.values()) - timedelta(days=7)
        codes = list(need_update.keys())

        print(f"\n开始采集（目标日期: {TARGET_DATE}）...")
        print(f"  并发窗口: {global_start} ~ {TARGET_DATE}, {len(codes)} 只ETF")
        start_time = time.time()

        provider = AkshareProvider(prefer_sina=True)
        df = provider.fetch_daily_bars(codes, global_start, TARGET_DATE)

        elapsed = time.time() - start_time
        print(f"  原始数据获取完成: {len(df)} 条, 耗时: {elapsed:.1f}s")

        if df.empty:
            print("❌ 未获取到任何数据")
            return

        # Filter to only dates after each ETF's latest date
        df = df[df["trade_date"] <= TARGET_DATE].copy()
        df["latest_date"] = df["etf_code"].map(latest_dates)
        df = df[df["trade_date"] > df["latest_date"]].copy()

        success = df["etf_code"].nunique()
        failed = [code for code in codes if code not in df["etf_code"].unique()]

        print(f"\n采集完成: 成功 {success} 只, 失败 {len(failed)} 只")
        if failed:
            print(f"失败示例: {failed[:10]}")

        # Clean and prepare records
        def _clean(v):
            if v is None or pd.isna(v):
                return None
            if isinstance(v, int | float):
                return float(v)
            return v

        records = []
        for _, row in df.iterrows():
            record = {
                "etf_code": row.get("etf_code"),
                "trade_date": row.get("trade_date"),
                "open": _clean(row.get("open")),
                "high": _clean(row.get("high")),
                "low": _clean(row.get("low")),
                "close": _clean(row.get("close")),
                "volume": int(row.get("volume")) if pd.notna(row.get("volume")) else None,
                "amount": _clean(row.get("amount")),
                "change_pct": _clean(row.get("change_pct")),
                "turnover_rate": _clean(row.get("turnover_rate")),
            }
            records.append(record)

        if not records:
            print("❌ 无有效记录")
            return

        # UPSERT
        print("\n写入数据库...")
        stmt = (
            insert(InstrumentDailyBar)
            .values(records)
            .on_conflict_do_update(
                index_elements=["etf_code", "trade_date"],
                set_={
                    "open": insert(InstrumentDailyBar).excluded.open,
                    "high": insert(InstrumentDailyBar).excluded.high,
                    "low": insert(InstrumentDailyBar).excluded.low,
                    "close": insert(InstrumentDailyBar).excluded.close,
                    "volume": insert(InstrumentDailyBar).excluded.volume,
                    "amount": insert(InstrumentDailyBar).excluded.amount,
                    "change_pct": insert(InstrumentDailyBar).excluded.change_pct,
                    "turnover_rate": insert(InstrumentDailyBar).excluded.turnover_rate,
                },
            )
        )
        db.execute(stmt)
        db.commit()

        print(f"✅ 成功写入 {len(records)} 条日K记录")

        # Verify
        result = db.execute(text('''
            SELECT MAX(trade_date) as max_date, COUNT(DISTINCT etf_code) as etf_count
            FROM instrument_daily_bar
            WHERE trade_date = '2026-06-08'
        ''')).fetchone()
        print(f"\n验证: 2026-06-08 有 {result[1]} 只ETF的数据")

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
