"""补跑最近缺失日期的定时任务数据。

按正确顺序执行：
1. 数据采集 (daily_bar) - 每天15:30
2. 指标计算 (indicator) - 每天08:00
3. 评分计算 (score) - 每天08:30
4. 交易信号 (signal) - 每天09:00
"""

import os
import sys
import warnings
from datetime import date, timedelta

import pandas as pd

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.core.calendar import get_trading_dates
from app.data.indicators.calculator import batch_calculate_indicators
from app.data.providers.akshare_provider import AkshareProvider
from app.models.etf import InstrumentDailyBar, ETFIndicator
from app.services.scoring_service import ScoringService

settings = get_settings()
engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)

# 需要采集数据的ETF代码列表
ETF_CODES = ["159915.SZ", "512000.SH", "159928.SZ", "510300.SH", "510050.SH"]


def get_missing_dates(db, table, date_column, code_filter=None):
    """Find all trading days between latest date in table and yesterday."""
    if code_filter:
        max_result = db.query(func.max(date_column)).filter(code_filter).scalar()
    else:
        max_result = db.query(func.max(date_column)).scalar()

    start = max_result + timedelta(days=1) if max_result else date(2026, 1, 1)

    end = date.today() - timedelta(days=1)  # 昨天

    if start > end:
        return []

    # 只取交易日（使用中国A股交易日历）
    return get_trading_dates(start, end)


def fetch_and_insert_daily_bars_for_date(db, trade_date: date, provider: AkshareProvider):
    """Fetch daily bars for a single trading date."""
    print(f"\n  📅 Fetching daily bars for {trade_date}...")

    try:
        df = provider.fetch_daily_bars(ETF_CODES, trade_date, trade_date)
    except Exception as e:
        print(f"  ⚠️  fetch_daily_bars failed: {e}")
        return 0

    if df.empty:
        print(f"  ⚠️  No data returned for {trade_date}")
        return 0

    def _clean(v):
        if v is None or pd.isna(v):
            return None
        if isinstance(v, int | float):
            return float(v)
        return v

    records = []
    for _, row in df.iterrows():
        etf_code = row.get("etf_code")
        trade_date = row.get("trade_date")
        if not etf_code or not trade_date or pd.isna(etf_code) or pd.isna(trade_date):
            continue

        record = {
            "etf_code": str(etf_code),
            "trade_date": trade_date,
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
        print(f"  ⚠️  No valid records for {trade_date}")
        return 0

    # UPSERT
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

    # Count per ETF
    for code in ETF_CODES:
        count = df[df["etf_code"] == code].shape[0]
        if count > 0:
            print(f"    ✅ {code}: {count} record(s)")

    return len(records)


def run_indicators_for_date(db, trade_date: date):
    """Run indicator calculation for a specific date."""
    print(f"\n  📈 Calculating indicators for {trade_date}...")
    try:
        # Use batch_calculate_indicators which handles all ETFs
        # It uses the latest available data, so we need to ensure daily bars exist first
        count = batch_calculate_indicators(db)
        print(f"    ✅ Updated {count} ETF indicators")
        return count
    except Exception as e:
        print(f"    ❌ Error: {e}")
        return 0


def run_scores_for_date(db, trade_date: date):
    """Run score calculation for a specific date."""
    print(f"\n  🏆 Calculating scores for {trade_date}...")
    try:
        service = ScoringService(db)
        results = service.calculate_daily_scores()
        total = sum(results.values())
        print(f"    ✅ Updated {total} scores across {len(results)} templates")
        return total
    except Exception as e:
        print(f"    ❌ Error: {e}")
        return 0


def run_signals_for_date(db, trade_date: date):
    """Run signal generation for a specific date."""
    print(f"\n  ⚡ Generating signals for {trade_date}...")
    try:
        from sqlalchemy import text

        from app.services.signal_generator import generate_signals_for_strategy

        # Get all active strategies
        strategies = db.execute(
            text("SELECT id, name, strategy_type, params FROM strategy_config WHERE is_active = true")
        ).fetchall()

        if not strategies:
            print("    ℹ️  No active strategies found")
            return 0

        signal_rows = []
        total_signals = 0
        buy_count = sell_count = hold_count = 0
        signal_rows = []

        for strategy in strategies:
            strategy_id, name, strategy_type, params = strategy
            params = params or {}

            # Generate signals for each ETF
            for etf_code in ETF_CODES:
                signals = generate_signals_for_strategy(
                    db, etf_code, strategy_type, params, trade_date, lookback_days=60
                )

                for sig in signals:
                    signal_rows.append({
                        "strategy_id": strategy_id,
                        "etf_code": etf_code,
                        "trade_date": trade_date,
                        "signal_type": sig["type"],
                        "strength": sig["strength"],
                        "extra_data": None,
                    })
                    total_signals += 1
                    if sig["type"] == "BUY":
                        buy_count += 1
                    elif sig["type"] == "SELL":
                        sell_count += 1
                    else:
                        hold_count += 1

        if signal_rows:
            db.execute(text("""
                INSERT INTO signal (strategy_id, etf_code, trade_date, signal_type, strength, extra_data, created_at)
                VALUES (:strategy_id, :etf_code, :trade_date, :signal_type, :strength, :extra_data, NOW())
                ON CONFLICT (strategy_id, etf_code, trade_date) DO UPDATE SET
                    signal_type = EXCLUDED.signal_type,
                    strength = EXCLUDED.strength,
                    extra_data = EXCLUDED.extra_data,
                    created_at = NOW()
            """), signal_rows)

        db.commit()

        if total_signals > 0:
            print(f"    ✅ Generated {total_signals} signals: BUY={buy_count}, SELL={sell_count}, HOLD={hold_count}")
        else:
            print("    ℹ️  No signals generated")
        return total_signals
    except Exception as e:
        print(f"    ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return 0


def verify_data(db):
    """Print summary of data."""
    print("\n" + "=" * 60)
    print("📊 数据补跑完成 — 验证结果")
    print("=" * 60)

    # Daily bars per ETF
    print("\nDaily bars latest dates:")
    for code in ETF_CODES:
        max_date = db.execute(
            select(func.max(InstrumentDailyBar.trade_date))
            .where(InstrumentDailyBar.etf_code == code)
        ).scalar()
        count = db.execute(
            select(func.count())
            .where(InstrumentDailyBar.etf_code == code)
        ).scalar()
        print(f"  {code}: {count} days, latest={max_date}")

    # Indicator summary
    ind_count = db.execute(select(func.count()).select_from(ETFIndicator)).scalar()
    ind_max_date = db.execute(select(func.max(ETFIndicator.trade_date))).scalar()
    print(f"\nIndicators: {ind_count} records, latest={ind_max_date}")

    # Score summary
    score_count = db.execute(text("SELECT COUNT(*) FROM etf_score")).scalar()
    score_max_date = db.execute(text("SELECT MAX(trade_date) FROM etf_score")).scalar()
    print(f"Scores: {score_count} records, latest={score_max_date}")


def main():
    db = Session()
    try:
        print("=" * 60)
        print("🚀 ETF数据补跑任务启动")
        print("=" * 60)

        # Step 1: Determine date range
        latest_daily = db.query(func.max(InstrumentDailyBar.trade_date)).scalar()
        start_date = latest_daily + timedelta(days=1) if latest_daily else date(2026, 6, 1)

        end_date = date.today() - timedelta(days=1)

        if start_date > end_date:
            print(f"\n✅ Daily bars already up to date (latest: {latest_daily})")
        else:
            print(f"\n📅 需要补跑的日期范围: {start_date} ~ {end_date}")

            # Collect all trading days in the range using the A-share calendar
            trading_days = get_trading_dates(start_date, end_date)

            if not trading_days:
                print("\n✅ No trading days in the range (all weekends/holidays)")
            else:
                print(f"   共 {len(trading_days)} 个交易日: {', '.join(str(d) for d in trading_days)}")

                # Step 2: Fetch daily bars for each trading day
                print("\n" + "-" * 60)
                print("STEP 1: 数据采集 (Daily Bars)")
                print("-" * 60)
                provider = AkshareProvider()
                total_bars = 0
                provider = AkshareProvider()
                for trade_date in trading_days:
                    count = fetch_and_insert_daily_bars_for_date(db, trade_date, provider)
                    total_bars += count
                print(f"\n📊 Step 1 完成: 共插入/更新 {total_bars} 条日K记录")

                # Step 3: Calculate indicators
                print("\n" + "-" * 60)
                print("STEP 2: 指标计算 (Indicators)")
                print("-" * 60)
                # batch_calculate_indicators handles all dates automatically
                ind_count = run_indicators_for_date(db, end_date)
                print(f"\n📊 Step 2 完成: 共更新 {ind_count} 条指标记录")

                # Step 4: Calculate scores
                print("\n" + "-" * 60)
                print("STEP 3: 评分计算 (Scores)")
                print("-" * 60)
                score_count = run_scores_for_date(db, end_date)
                print(f"\n📊 Step 3 完成: 共更新 {score_count} 条评分记录")

                # Step 5: Generate signals for the last trading day
                print("\n" + "-" * 60)
                print("STEP 4: 交易信号 (Signals)")
                print("-" * 60)
                if trading_days:
                    last_trading_day = trading_days[-1]
                    sig_count = run_signals_for_date(db, last_trading_day)
                    print(f"\n📊 Step 4 完成: 共生成 {sig_count} 个交易信号")

        # Verify
        verify_data(db)

        print("\n" + "=" * 60)
        print("🎉 数据补跑任务全部完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
