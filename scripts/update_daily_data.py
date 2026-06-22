"""增量更新 daily_bar、indicator、score、signal、backtest 数据到最新日期.

获取所有活跃 ETF 的缺失日期历史数据，重新计算技术指标、评分、信号和回测.
"""

import os
import sys
import time
import warnings
from datetime import date, timedelta

import pandas as pd

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.data.indicators.calculator import batch_calculate_indicators
from app.data.providers.akshare_provider import AkshareProvider
from app.models.etf import ETFDailyBar, ETFIndicator, ETFInfo
from app.models.etl import BacktestResult, Signal, StrategyConfig
from app.services.backtest_service import BacktestService
from app.services.scoring_service import ScoringService
from app.services.signal_service import SignalService

settings = get_settings()
engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)

# Batch size for fetching daily bars — small to avoid API rate limits
_BATCH_SIZE = 10
# Delay between batches (seconds) to avoid overwhelming the API
_BATCH_DELAY = 3.0


def _get_active_etf_codes(db) -> list:
    """Get all active ETF codes from the database."""
    return db.execute(
        select(ETFInfo.code).where(ETFInfo.status == "active")
    ).scalars().all()


def _get_etf_latest_date(db, etf_code: str) -> date | None:
    """Get the latest trade date for a specific ETF."""
    result = db.execute(
        select(func.max(ETFDailyBar.trade_date))
        .where(ETFDailyBar.etf_code == etf_code)
    ).scalar()
    return result


def fetch_and_insert_daily_bars(db, end_date: date):
    """Fetch missing daily bars from akshare for all active ETFs and insert into DB.

    For each ETF, determines its own start date based on its latest bar.
    """
    etf_codes = _get_active_etf_codes(db)
    if not etf_codes:
        print("❌ No active ETFs found")
        return 0

    print(f"\n📊 Step 1: Fetching daily bars for {len(etf_codes)} ETFs up to {end_date}...")
    provider = AkshareProvider()

    total_records = 0
    total_fetched = 0
    etfs_updated = 0

    # Process in batches to avoid API overload
    for i in range(0, len(etf_codes), _BATCH_SIZE):
        batch = etf_codes[i : i + _BATCH_SIZE]
        batch_num = i // _BATCH_SIZE + 1
        total_batches = (len(etf_codes) + _BATCH_SIZE - 1) // _BATCH_SIZE
        print(f"   Batch {batch_num}/{total_batches}: {len(batch)} ETFs")

        # Determine per-ETF start dates for this batch
        batch_with_dates = []
        for code in batch:
            latest = _get_etf_latest_date(db, code)
            start = latest + timedelta(days=1) if latest else date(2025, 1, 1)
            if start <= end_date:
                batch_with_dates.append((code, start))

        if not batch_with_dates:
            continue

        # Use the earliest start date in the batch for the API call
        batch_start = min(start for _, start in batch_with_dates)

        try:
            df = provider.fetch_daily_bars([code for code, _ in batch_with_dates], batch_start, end_date)
        except Exception as exc:
            print(f"   ⚠️ Batch failed: {exc}")
            continue

        if df.empty:
            continue

        total_fetched += len(df)

        # Build records, filtering to only include data after each ETF's latest date
        records = []
        for _, row in df.iterrows():
            code = row.get("etf_code")
            trade_date = row.get("trade_date")
            if not code or not trade_date:
                continue

            # Find this ETF's start date
            etf_start = next((s for c, s in batch_with_dates if c == code), None)
            if etf_start and trade_date < etf_start:
                continue

            def _clean(v):
                if v is None or pd.isna(v):
                    return None
                if isinstance(v, int | float):
                    return float(v)
                return v

            record = {
                "etf_code": code,
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
            record = {k: v for k, v in record.items() if v is not None}
            records.append(record)

        if not records:
            continue

        # Use ON CONFLICT DO UPDATE to handle duplicates
        stmt = (
            insert(ETFDailyBar)
            .values(records)
            .on_conflict_do_update(
                index_elements=["etf_code", "trade_date"],
                set_={
                    "open": insert(ETFDailyBar).excluded.open,
                    "high": insert(ETFDailyBar).excluded.high,
                    "low": insert(ETFDailyBar).excluded.low,
                    "close": insert(ETFDailyBar).excluded.close,
                    "volume": insert(ETFDailyBar).excluded.volume,
                    "amount": insert(ETFDailyBar).excluded.amount,
                    "change_pct": insert(ETFDailyBar).excluded.change_pct,
                    "turnover_rate": insert(ETFDailyBar).excluded.turnover_rate,
                },
            )
        )
        db.execute(stmt)
        db.commit()
        total_records += len(records)
        etfs_updated += len({r["etf_code"] for r in records})

        # Rate limit: delay between batches
        if i + _BATCH_SIZE < len(etf_codes):
            time.sleep(_BATCH_DELAY)

    print(f"   Fetched {total_fetched} raw records, inserted/updated {total_records} for {etfs_updated} ETFs")
    return total_records


def run_indicator_calculation(db):
    """Recalculate indicators for all active ETFs."""
    print("\n📈 Step 2: Recalculating technical indicators...")
    count = batch_calculate_indicators(db)
    print(f"   Updated {count} ETF indicators")
    return count


def run_score_calculation(db):
    """Recalculate composite scores."""
    print("\n🏆 Step 3: Recalculating composite scores...")
    service = ScoringService(db)
    results = service.calculate_daily_scores()
    total = sum(results.values())
    print(f"   Updated {total} scores across {len(results)} templates")
    return total


def run_signal_generation(db):
    """Generate trading signals for all active strategies."""
    print("\n📡 Step 4: Generating trading signals...")

    # Get latest trade date from daily bars
    latest_date = db.execute(
        select(func.max(ETFDailyBar.trade_date))
    ).scalar()
    if not latest_date:
        print("   ⚠️ No daily bar data available, skipping signal generation")
        return 0

    # Get active strategies
    strategies = db.execute(
        select(StrategyConfig).where(StrategyConfig.is_active.is_(True))
    ).scalars().all()
    if not strategies:
        print("   ⚠️ No active strategies found, skipping signal generation")
        return 0

    # Get ETFs that actually have daily bar data (not all active ETFs)
    etfs_with_bars = db.execute(
        select(ETFDailyBar.etf_code)
        .where(ETFDailyBar.trade_date == latest_date)
        .distinct()
    ).scalars().all()
    if not etfs_with_bars:
        print("   ⚠️ No ETFs with daily bar data found, skipping signal generation")
        return 0

    signal_service = SignalService(db)
    total_signals = 0
    skipped = 0

    # Pre-load existing signals for the latest date to avoid per-pair DB queries
    existing_keys = set(
        db.execute(
            select(Signal.strategy_id, Signal.etf_code).where(Signal.trade_date == latest_date)
        ).all()
    )

    for strategy in strategies:
        for etf_code in etfs_with_bars:
            if (strategy.id, etf_code) in existing_keys:
                skipped += 1
                continue
            try:
                signals = signal_service.generate_signals(
                    strategy_id=strategy.id,
                    etf_code=etf_code,
                    strategy_type=strategy.strategy_type,
                    params=strategy.params or {},
                    trade_date=latest_date,
                )
                total_signals += len(signals)
            except Exception as exc:
                print(f"   ⚠️ Signal failed for {etf_code} / {strategy.name}: {exc}")

    print(
        f"   Generated {total_signals} signals for {len(strategies)} strategies × "
        f"{len(etfs_with_bars)} ETFs (skipped {skipped} existing)"
    )
    return total_signals


def run_backtests(db):
    """Run backtests for all active strategies on ETFs with daily bar data."""
    print("\n📊 Step 5: Running backtests...")

    strategies = db.execute(
        select(StrategyConfig).where(StrategyConfig.is_active.is_(True))
    ).scalars().all()
    if not strategies:
        print("   ⚠️ No active strategies found, skipping backtests")
        return 0

    # Get ETFs with daily bar data
    etfs_with_bars = db.execute(
        select(ETFDailyBar.etf_code).distinct()
    ).scalars().all()
    if not etfs_with_bars:
        print("   ⚠️ No ETFs with daily bar data found, skipping backtests")
        return 0

    service = BacktestService(db)
    total = 0
    skipped = 0

    # Only re-run backtests that haven't been run in the last 7 days
    lookback_until = date.today() - timedelta(days=7)
    recent_backtests = set(
        db.execute(
            select(BacktestResult.strategy_id, BacktestResult.etf_code)
            .where(BacktestResult.created_at >= lookback_until)
        ).all()
    )

    for strategy in strategies:
        for etf_code in etfs_with_bars:
            if (strategy.id, etf_code) in recent_backtests:
                skipped += 1
                continue
            try:
                service.run_backtest(
                    strategy_id=strategy.id,
                    etf_code=etf_code,
                    strategy_type=strategy.strategy_type,
                    params=strategy.params or {},
                    start_date=date(2025, 1, 2),
                    end_date=date.today() - timedelta(days=1),
                )
                total += 1
            except Exception as exc:
                print(f"   ⚠️ Backtest failed for {etf_code} / {strategy.name}: {exc}")

    print(f"   Completed {total} backtests (skipped {skipped} recent)")
    return total


def verify_data(db):
    """Print summary of updated data."""
    print("\n✅ Data Update Summary:")
    print("-" * 50)

    # ETFs with daily bars
    bar_etfs = db.execute(
        select(func.count(ETFDailyBar.etf_code.distinct()))
    ).scalar()
    bar_max = db.execute(select(func.max(ETFDailyBar.trade_date))).scalar()
    print(f"   Daily bars: {bar_etfs} ETFs, latest={bar_max}")

    # Indicator summary
    ind_count = db.execute(select(func.count()).select_from(ETFIndicator)).scalar()
    ind_max_date = db.execute(select(func.max(ETFIndicator.trade_date))).scalar()
    print(f"   Indicators: {ind_count} records, latest={ind_max_date}")

    # Score summary
    score_count = db.execute(text("SELECT COUNT(*) FROM etf_score")).scalar()
    score_max_date = db.execute(text("SELECT MAX(trade_date) FROM etf_score")).scalar()
    print(f"   Scores: {score_count} records, latest={score_max_date}")

    # Signal summary
    sig_latest = db.execute(text("SELECT MAX(trade_date) FROM signal")).scalar()
    sig_count = db.execute(text("SELECT COUNT(*) FROM signal WHERE trade_date = :d"), {"d": sig_latest}).scalar()
    print(f"   Signals: {sig_count} records for {sig_latest}")

    # Backtest summary
    bt_count = db.execute(text("SELECT COUNT(*) FROM backtest_result")).scalar()
    bt_max = db.execute(text("SELECT MAX(created_at) FROM backtest_result")).scalar()
    print(f"   Backtests: {bt_count} records, latest={bt_max}")


def main():
    db = Session()
    try:
        end_date = date.today() - timedelta(days=1)
        count = fetch_and_insert_daily_bars(db, end_date)
        print(f"   Inserted/updated {count} daily bar records")

        # Recalculate indicators
        ind_count = run_indicator_calculation(db)
        print(f"   已更新 {ind_count} 条指标记录")

        # Recalculate scores
        score_count = run_score_calculation(db)
        print(f"   已更新 {score_count} 条评分记录")

        # Generate signals
        signal_count = run_signal_generation(db)
        print(f"   已生成 {signal_count} 个信号")

        # Run backtests
        backtest_count = run_backtests(db)
        print(f"   已完成 {backtest_count} 个回测")

        # Verify
        verify_data(db)

        print("\n🎉 All data updated successfully!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
