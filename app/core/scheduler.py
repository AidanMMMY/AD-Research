"""APScheduler background task scheduler.

Provides scheduled execution of daily ETL, indicator calculation,
scoring, report generation, market scan, and signal generation jobs.
"""

from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.database import SessionLocal
from app.core.redis_client import redis_lock
from app.data.indicators.calculator import batch_calculate_indicators
from app.data.pipelines.a_share import AShareETLPipeline
from app.data.pipelines.a_share_stock_daily import AStockDailyPipeline
from app.data.pipelines.a_share_stock_discovery import AShareStockDiscoveryPipeline
from app.data.pipelines.a_share_stock_financials import AStockFinancialsPipeline
from app.data.pipelines.a_share_stock_fundamental import AStockFundamentalPipeline
from app.data.pipelines.crypto_daily import CryptoDailyPipeline
from app.data.pipelines.etf_metadata_enrichment import ETFMetadataEnrichmentPipeline
from app.data.pipelines.us_backfill import USHistoricalBackfillPipeline
from app.data.pipelines.us_etf import USDailyPipeline
from app.data.pipelines.us_etf_discovery import USEtfDiscoveryPipeline
from app.data.pipelines.us_stock_discovery import USStockDiscoveryPipeline
from app.data.pipelines.us_stock_enrichment import USStockEnrichmentPipeline
from app.models.etf import ETFInfo
from app.models.pool import ETFPools
from app.services.etf_scanner_service import ETFScannerService
from app.services.report_service import ReportService
from app.services.scoring_service import ScoringService
from app.services.signal_service import SignalService
from app.services.strategy_service import StrategyService

scheduler = BackgroundScheduler()

# Names for distributed locks used by scheduled jobs.
_LOCK_ETL = "daily_etl"
_LOCK_DAILY_PIPELINE = "daily_pipeline"


def run_a_share_etl(target_date: date | None = None, prefer_sina: bool = False):
    """Run the A-share ETF daily ETL pipeline.

    Args:
        target_date: If provided, fetch bars for this date instead of yesterday.
            Useful for backfilling missed runs.
        prefer_sina: If True, prefer Sina data source over East Money (more
            stable for bulk backfills).
    """
    with redis_lock(_LOCK_DAILY_PIPELINE, expire_seconds=3600) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] A-share ETL skipped: daily pipeline lock in use")
            return

        db = SessionLocal()
        try:
            pipeline = AShareETLPipeline(db, target_date=target_date, prefer_sina=prefer_sina)
            result = pipeline.run_with_retry(max_attempts=3)
            print(
                f"[Scheduler] A-share ETL (target={target_date}, sina={prefer_sina}): success={result.success}, records={result.records}"
            )
        finally:
            db.close()


def run_a_share_stock_etl(target_date: date | None = None):
    """Run the A-share individual stock daily ETL pipeline.

    Fetches daily OHLCV bars for all active A-share individual stocks
    using Tushare as the data source.

    Scheduled at 16:00 Beijing time (1 hour after A-share market close).

    Args:
        target_date: If provided, fetch bars for this date instead of yesterday.
    """
    with redis_lock("a_stock_daily_pipeline", expire_seconds=7200) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] A-stock daily ETL skipped: lock in use")
            return

        db = SessionLocal()
        try:
            pipeline = AStockDailyPipeline(db, target_date=target_date)
            result = pipeline.run_with_retry(max_attempts=3)
            print(
                f"[Scheduler] A-stock daily ETL (target={target_date}): "
                f"success={result.success}, records={result.records}"
            )
        finally:
            db.close()


def run_a_share_stock_fundamental(target_date: date | None = None):
    """Run the A-share individual stock fundamental/valuation ETL pipeline.

    Fetches daily_basic (PE, PB, market cap, turnover) from Tushare
    for all A-share stocks. Uses the market-wide endpoint for efficiency.

    Scheduled at 16:30 daily (after the daily bar ETL completes).

    Args:
        target_date: If provided, fetch fundamentals for this date instead of yesterday.
    """
    with redis_lock("a_stock_fundamental_pipeline", expire_seconds=3600) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] A-stock fundamental ETL skipped: lock in use")
            return

        db = SessionLocal()
        try:
            pipeline = AStockFundamentalPipeline(db, target_date=target_date)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] A-stock fundamental ETL (target={target_date}): "
                f"success={result.success}, records={result.records}"
            )
        finally:
            db.close()


def run_a_share_stock_discovery():
    """Run the A-share individual stock discovery pipeline (weekly Monday 01:00).

    Fetches the full A-share stock list from Tushare stock_basic across
    SSE, SZSE, and BSE, and upserts into etf_info.
    """
    with redis_lock("a_stock_discovery", expire_seconds=7200) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] A-share stock discovery skipped: lock in use")
            return
        db = SessionLocal()
        try:
            pipeline = AShareStockDiscoveryPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] A-share stock discovery: "
                f"success={result.success}, records={result.records}"
            )
        finally:
            db.close()


def run_a_share_stock_financials():
    """Run the A-share individual stock financial statements pipeline (weekly Monday 02:00).

    Fetches quarterly income statements and balance sheets from Tushare
    income_vip and balancesheet_vip endpoints. Processes a rotating batch
    of ~50 stocks per run to stay within rate limits.
    """
    with redis_lock("a_stock_financials", expire_seconds=7200) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] A-share stock financials skipped: lock in use")
            return
        db = SessionLocal()
        try:
            pipeline = AStockFinancialsPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] A-share stock financials: "
                f"success={result.success}, records={result.records}"
            )
        finally:
            db.close()


def run_us_etl(target_date: date | None = None):
    """Run the US equity daily ETL pipeline.

    Fetches daily OHLCV bars for all active US instruments (ETFs + stocks)
    using FMP as primary with Tiingo fallback.

    Scheduled at 05:00 Beijing time (17:00 ET, 1 hour after US market close).

    Args:
        target_date: If provided, fetch bars for this date instead of yesterday.
    """
    with redis_lock("us_daily_pipeline", expire_seconds=3600) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] US ETL skipped: US pipeline lock in use")
            return

        db = SessionLocal()
        try:
            pipeline = USDailyPipeline(db, target_date=target_date)
            result = pipeline.run_with_retry(max_attempts=3)
            print(
                f"[Scheduler] US ETL (target={target_date}): "
                f"success={result.success}, records={result.records}"
            )
        finally:
            db.close()


def run_us_historical_backfill():
    """Run a small batch of US equity historical backfill.

    Processes ~15 instruments per run, rotating through the full list of
    active US instruments. Designed to stay within Tiingo free tier limits
    (50 req/hour, 500 symbols/month) while steadily filling historical gaps.

    Scheduled every hour. Instruments that Tiingo misses are retried with
    yfinance in the same run so that multiple data sources cover the batch.
    """
    with redis_lock("us_backfill_pipeline", expire_seconds=7200) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] US historical backfill skipped: lock in use")
            return

        db = SessionLocal()
        try:
            pipeline = USHistoricalBackfillPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] US historical backfill: "
                f"success={result.success}, records={result.records}"
            )
        finally:
            db.close()


def run_us_indicator_calculation(target_date: date | None = None):
    """Run indicator calculation specifically for US instruments.

    Runs after the US ETL completes. Only processes US-market instruments
    to avoid redundant calculation of A-share / Crypto instruments.

    Args:
        target_date: If provided, calculate indicators up to this date.
    """
    # Wait for US pipeline lock to be released
    with redis_lock("us_daily_pipeline", expire_seconds=3600, wait_timeout=1800) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] US indicator calculation skipped: could not acquire pipeline lock")
            return

        db = SessionLocal()
        try:
            count = batch_calculate_indicators(
                db, target_date=target_date, full_history=False, market_filter="US"
            )
            print(
                f"[Scheduler] US indicator calculation (target={target_date}): "
                f"{count} records updated"
            )
        finally:
            db.close()


def run_indicator_calculation(target_date: date | None = None, full_history: bool = False):
    """Run the batch indicator calculation for A-share instruments.

    US and Crypto instruments have their own indicator calculation jobs
    (run_us_indicator_calculation, run_crypto_indicator_calculation) that
    run immediately after their respective ETL pipelines.

    Args:
        target_date: If provided, calculate indicators up to this date.
        full_history: If True, upsert indicators for every historical trade
            date instead of only the latest day. Useful for backfilling.
    """
    # Wait for the daily ETL lock to be released to avoid calculating
    # indicators while bars are still being written.
    with redis_lock(_LOCK_DAILY_PIPELINE, expire_seconds=3600, wait_timeout=1800) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Indicator calculation skipped: could not acquire pipeline lock")
            return

        db = SessionLocal()
        try:
            count = batch_calculate_indicators(
                db, target_date=target_date, full_history=full_history, market_filter="A股"
            )
            print(
                f"[Scheduler] Indicator calculation (target={target_date}, "
                f"full_history={full_history}): {count} records updated"
            )
        finally:
            db.close()


def run_score_calculation(target_date: date | None = None):
    """Run the daily ETF composite score calculation for all templates.

    Args:
        target_date: If provided, calculate scores for this date.
    """
    with redis_lock(_LOCK_DAILY_PIPELINE, expire_seconds=1800, wait_timeout=1800) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Score calculation skipped: could not acquire pipeline lock")
            return

        db = SessionLocal()
        try:
            service = ScoringService(db)
            results = service.calculate_daily_scores(trade_date=target_date)
            total = sum(results.values())
            print(f"[Scheduler] Score calculation (target={target_date}): {total} scores across {len(results)} templates")
        finally:
            db.close()


def run_weekly_pool_reports():
    """Generate weekly reports for all ETF pools (Sunday 22:00)."""
    with redis_lock("weekly_pool_reports", expire_seconds=3600) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Weekly pool reports skipped: lock in use")
            return
        db = SessionLocal()
        try:
            service = ReportService(db)
            pools = db.query(ETFPools).all()
            for pool in pools:
                try:
                    metadata = service.generate_pool_report(
                        pool_id=pool.id,
                        report_type="pool_weekly",
                        format="html",
                    )
                    print(
                        f"[Scheduler] Weekly report for pool {pool.id}: {metadata.status}"
                    )
                except Exception as e:
                    print(f"[Scheduler] Failed to generate report for pool {pool.id}: {e}")
        finally:
            db.close()


def run_us_etf_discovery():
    """Run the US ETF discovery pipeline (weekly Sunday 01:00).

    Fetches the curated US ETF list from Finnhub and upserts them as
    instrument_type="ETF", market="US" into etf_info, keeping category
    metadata in sync.
    """
    with redis_lock("us_etf_discovery", expire_seconds=7200) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] US ETF discovery skipped: lock in use")
            return
        db = SessionLocal()
        try:
            pipeline = USEtfDiscoveryPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] US ETF discovery: success={result.success}, "
                f"records={result.records}"
            )
        finally:
            db.close()


def run_us_stock_discovery():
    """Run the US stock discovery pipeline (weekly Sunday 02:00).

    Fetches S&P 500 constituents from FMP and upserts them as
    instrument_type="STOCK", market="US" into etf_info.
    """
    with redis_lock("us_stock_discovery", expire_seconds=7200) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] US stock discovery skipped: lock in use")
            return
        db = SessionLocal()
        try:
            pipeline = USStockDiscoveryPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] US stock discovery: success={result.success}, "
                f"records={result.records}"
            )
        finally:
            db.close()


def run_us_stock_enrichment():
    """Run the US stock metadata enrichment pipeline (daily 02:30).

    Backfills missing sector/industry/category for US individual stocks
    from the public S&P 500 CSV.  Uses a small batch size to stay
    within upstream rate limits and to finish quickly.
    """
    with redis_lock("us_stock_enrichment", expire_seconds=1800) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] US stock enrichment skipped: lock in use")
            return
        db = SessionLocal()
        try:
            pipeline = USStockEnrichmentPipeline(db, batch_size=200)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] US stock enrichment: success={result.success}, "
                f"records={result.records}"
            )
        finally:
            db.close()


def run_etf_scan():
    """Run the ETF market scan (Sunday 03:00)."""
    with redis_lock("etf_scan", expire_seconds=7200) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] ETF scan skipped: lock in use")
            return
        db = SessionLocal()
        try:
            service = ETFScannerService(db)
            result = service.scan_market()
            total = len(result.get("new", [])) + len(result.get("delisted", [])) + len(result.get("changed", []))
            print(f"[Scheduler] ETF scan: {total} changes found")
        finally:
            db.close()


def run_etf_metadata_enrichment():
    """Run the ETF metadata enrichment pipeline (Sunday 04:00).

    Fills missing ETF product metadata (manager, category, underlying index,
    fund size, inception_date, list_date) from Tushare fund_basic.
    """
    with redis_lock("etf_metadata_enrichment", expire_seconds=7200) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] ETF metadata enrichment skipped: lock in use")
            return
        db = SessionLocal()
        try:
            pipeline = ETFMetadataEnrichmentPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] ETF metadata enrichment: "
                f"success={result.success}, records={result.records}"
            )
        finally:
            db.close()


def run_crypto_etl(target_date: date | None = None):
    """Run the cryptocurrency daily ETL pipeline.

    Crypto markets are 24/7.  Runs at 00:05 UTC daily to capture the
    previous day's complete daily candle (midnight UTC boundary).

    Args:
        target_date: If provided, fetch bars for this date instead of yesterday.
    """
    with redis_lock("crypto_daily_pipeline", expire_seconds=3600) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Crypto ETL skipped: lock in use")
            return

        db = SessionLocal()
        try:
            pipeline = CryptoDailyPipeline(db, target_date=target_date)
            result = pipeline.run_with_retry(max_attempts=3)
            print(
                f"[Scheduler] Crypto ETL (target={target_date}): "
                f"success={result.success}, records={result.records}"
            )
        finally:
            db.close()


def run_crypto_indicator_calculation(target_date: date | None = None):
    """Run indicator calculation for cryptocurrency instruments.

    Waits for the crypto ETL lock to be released before calculating.

    Args:
        target_date: If provided, calculate indicators up to this date.
    """
    with redis_lock(
        "crypto_daily_pipeline", expire_seconds=3600, wait_timeout=1800
    ) as acquired:
        if not acquired:
            print(
                "⚠️ [SCHEDULER_WARN] Crypto indicator calculation skipped: "
                "could not acquire pipeline lock"
            )
            return

        db = SessionLocal()
        try:
            count = batch_calculate_indicators(
                db, target_date=target_date, full_history=False, market_filter="CRYPTO"
            )
            print(
                f"[Scheduler] Crypto indicator (target={target_date}): "
                f"{count} records updated"
            )
        finally:
            db.close()


def run_paper_trade_market_update():
    """Update market values for all active paper-trade positions (hourly).

    Fetches latest Binance prices and recalculates unrealized PnL for every
    position with quantity > 0 across all active accounts.
    """
    with redis_lock(
        "paper_trade_market_update", expire_seconds=600
    ) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Paper trade market update skipped: lock in use")
            return
        db = SessionLocal()
        try:
            from app.services.paper_trading_service import PaperTradingService

            service = PaperTradingService(db)
            updated = service.update_market_values()
            print(f"[Scheduler] Paper trade market update: {updated} positions refreshed")
        finally:
            db.close()


def run_paper_trade_auto():
    """Auto-execute paper trades from today's BUY/SELL signals.

    Runs once daily after signal generation.  Each BUY signal allocates ~10%
    of account equity; each SELL signal closes the full position.

    Waits for the daily_pipeline lock (held by signal generation at 09:00)
    to be released before executing, ensuring signals are fully generated.
    """
    # Wait for signal generation to complete before trading
    with redis_lock(
        _LOCK_DAILY_PIPELINE, expire_seconds=3600, wait_timeout=3600
    ) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Paper trade auto skipped: signal generation still running after 1h")
            return

    with redis_lock(
        "paper_trade_auto", expire_seconds=1800, wait_timeout=600
    ) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Paper trade auto skipped: lock in use")
            return
        db = SessionLocal()
        try:
            from app.services.paper_trading_service import PaperTradingService

            service = PaperTradingService(db)
            accounts = service.get_accounts()
            total_orders = 0
            for acct in accounts:
                try:
                    orders = service.auto_trade_from_signals(acct.id)
                    total_orders += len(orders)
                except Exception:
                    continue
            print(
                f"[Scheduler] Paper trade auto: {total_orders} orders "
                f"across {len(accounts)} accounts"
            )
        finally:
            db.close()


def run_signal_generation(target_date: date | None = None):
    """Generate trading signals for all active strategies (daily 09:00).

    Args:
        target_date: If provided, generate signals for this date instead of today.
    """
    db = SessionLocal()
    try:
        strategy_service = StrategyService(db)
        signal_service = SignalService(db)
        strategies = strategy_service.get_strategies()
        active_strategies = [s for s in strategies if s.get("is_active")]

        # Get all active ETFs (previously capped at 50, which contradicted docs).
        etfs = db.query(ETFInfo).filter(ETFInfo.status == "active").all()
    finally:
        db.close()

    expire_seconds = max(1800, min(14400, len(active_strategies) * len(etfs) * 2))

    with redis_lock(_LOCK_DAILY_PIPELINE, expire_seconds=expire_seconds, wait_timeout=1800) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Signal generation skipped: could not acquire pipeline lock")
            return

        db = SessionLocal()
        try:
            trade_date = target_date or date.today()
            total_signals = 0
            for strategy in active_strategies:
                for etf in etfs:
                    try:
                        signals = signal_service.generate_signals(
                            strategy_id=strategy["id"],
                            etf_code=etf.code,
                            strategy_type=strategy["strategy_type"],
                            params=strategy["params"],
                            trade_date=trade_date,
                        )
                        total_signals += len(signals)
                    except Exception as e:
                        print(f"[Scheduler] Signal generation failed for {etf.code}: {e}")

            print(f"[Scheduler] Signal generation (target={target_date}): {total_signals} signals generated")
        finally:
            db.close()


def init_scheduler():
    """Initialize and start the background scheduler.

    Registers cron jobs:
      - US ETL at 05:00 daily (Beijing time = 17:00 ET, post-market)
      - US ETF discovery weekly Sunday 01:00
      - US stock discovery weekly Sunday 02:00
      - US historical backfill every hour
      - US indicator calculation at 05:30 daily (US market only)
      - A-share ETF ETL at 15:30 daily
      - A-share stock ETL at 16:00 daily
      - A-share stock fundamental at 16:30 daily
      - A-share stock discovery weekly Monday 01:00
      - A-share stock financials weekly Monday 02:00
      - Indicator calculation at 08:00 daily (A-share market only)
      - Score calculation at 08:30 daily
      - Weekly pool reports on Sunday at 22:00
      - ETF market scan on Sunday at 03:00
      - Signal generation at 09:00 daily
      - Paper trade auto at 09:30 daily (waits for signal generation)
      - Crypto ETL at 08:05 daily (00:05 UTC, post-UTC-midnight)
      - Crypto indicator calculation at 08:30 daily
    """
    scheduler.add_job(
        run_us_etl,
        trigger=CronTrigger(hour=5, minute=0, timezone="Asia/Shanghai"),
        id="us_daily_etl",
        name="美股日终采集",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_us_historical_backfill,
        trigger=CronTrigger(hour="*", minute=0, timezone="Asia/Shanghai"),
        id="us_historical_backfill",
        name="美股历史数据回填",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_us_indicator_calculation,
        trigger=CronTrigger(hour=5, minute=30, timezone="Asia/Shanghai"),
        id="us_indicator_calculation",
        name="美股指标批量计算",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_a_share_etl,
        trigger=CronTrigger(hour=15, minute=30, timezone="Asia/Shanghai"),
        id="a_share_daily_etl",
        name="A股ETF日终采集",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_indicator_calculation,
        trigger=CronTrigger(hour=8, minute=0, timezone="Asia/Shanghai"),
        id="indicator_calculation",
        name="指标批量计算",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_score_calculation,
        trigger=CronTrigger(hour=8, minute=30, timezone="Asia/Shanghai"),
        id="score_calculation",
        name="评分日终计算",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_weekly_pool_reports,
        trigger=CronTrigger(day_of_week="sun", hour=22, minute=0, timezone="Asia/Shanghai"),
        id="weekly_pool_reports",
        name="池周报生成",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_us_etf_discovery,
        trigger=CronTrigger(day_of_week="sun", hour=1, minute=0, timezone="Asia/Shanghai"),
        id="us_etf_discovery",
        name="美股ETF发现",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_us_stock_discovery,
        trigger=CronTrigger(day_of_week="sun", hour=2, minute=0, timezone="Asia/Shanghai"),
        id="us_stock_discovery",
        name="美股个股发现",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.add_job(
        run_us_stock_enrichment,
        trigger=CronTrigger(hour=2, minute=30, timezone="Asia/Shanghai"),
        id="us_stock_enrichment",
        name="美股个股元数据补全",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_etf_scan,
        trigger=CronTrigger(day_of_week="sun", hour=3, minute=0, timezone="Asia/Shanghai"),
        id="etf_market_scan",
        name="全市场ETF扫描",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_signal_generation,
        trigger=CronTrigger(hour=9, minute=0, timezone="Asia/Shanghai"),
        id="signal_generation",
        name="交易信号生成",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_crypto_etl,
        trigger=CronTrigger(hour=8, minute=5, timezone="Asia/Shanghai"),
        id="crypto_daily_etl",
        name="加密货币日终采集",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_crypto_indicator_calculation,
        trigger=CronTrigger(hour=8, minute=30, timezone="Asia/Shanghai"),
        id="crypto_indicator_calculation",
        name="加密货币指标计算",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_etf_metadata_enrichment,
        trigger=CronTrigger(day_of_week="sun", hour=4, minute=0, timezone="Asia/Shanghai"),
        id="etf_metadata_enrichment",
        name="ETF元数据补全",
        replace_existing=True,
        max_instances=1,
    )
    # ── Paper Trading Jobs ──
    scheduler.add_job(
        run_paper_trade_market_update,
        trigger=CronTrigger(hour="*", minute=15, timezone="Asia/Shanghai"),
        id="paper_trade_market_update",
        name="模拟仓市值更新",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_paper_trade_auto,
        trigger=CronTrigger(hour=9, minute=30, timezone="Asia/Shanghai"),
        id="paper_trade_auto",
        name="模拟仓信号自动交易",
        replace_existing=True,
        max_instances=1,
    )
    # ── A-Share Individual Stock Jobs ──
    scheduler.add_job(
        run_a_share_stock_etl,
        trigger=CronTrigger(hour=16, minute=0, timezone="Asia/Shanghai"),
        id="a_stock_daily_etl",
        name="A股个股日终采集",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_a_share_stock_fundamental,
        trigger=CronTrigger(hour=16, minute=30, timezone="Asia/Shanghai"),
        id="a_stock_fundamental_etl",
        name="A股个股估值数据采集",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_a_share_stock_discovery,
        trigger=CronTrigger(day_of_week="mon", hour=1, minute=0, timezone="Asia/Shanghai"),
        id="a_stock_discovery",
        name="A股个股发现",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_a_share_stock_financials,
        trigger=CronTrigger(day_of_week="mon", hour=2, minute=0, timezone="Asia/Shanghai"),
        id="a_stock_financials",
        name="A股个股财报采集",
        replace_existing=True,
        max_instances=1,
    )
    # ── News / Sentiment Jobs ──
    # A-share RSS feeds (every 5 minutes)
    try:
        from app.services.news.scheduler_jobs import (
            run_xinhua_crawl, run_cninfo_crawl, run_sina_crawl,
            run_yahoo_crawl, run_cnbc_crawl, run_sec_edgar_crawl,
            run_reddit_crawl,
        )
        scheduler.add_job(
            run_xinhua_crawl,
            trigger=IntervalTrigger(minutes=5),
            id="news_xinhua_5m",
            name="新华财经RSS",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_cninfo_crawl,
            trigger=IntervalTrigger(minutes=10),
            id="news_cninfo_10m",
            name="巨潮公告",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_sina_crawl,
            trigger=IntervalTrigger(minutes=5),
            id="news_sina_5m",
            name="新浪财经",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_yahoo_crawl,
            trigger=IntervalTrigger(minutes=5),
            id="news_yahoo_5m",
            name="Yahoo Finance RSS",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_cnbc_crawl,
            trigger=IntervalTrigger(minutes=5),
            id="news_cnbc_5m",
            name="CNBC RSS",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_sec_edgar_crawl,
            trigger=IntervalTrigger(minutes=30),
            id="news_sec_edgar_30m",
            name="SEC EDGAR 公告",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_reddit_crawl,
            trigger=IntervalTrigger(minutes=5),
            id="news_reddit_5m",
            name="Reddit 散户讨论",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    except ImportError:
        pass

    # Xueqiu (every 5 minutes; needs XUEQIU_COOKIE env)
    try:
        from app.services.news.scheduler_xueqiu_sync import run_xueqiu_crawl_sync
        scheduler.add_job(
            run_xueqiu_crawl_sync,
            trigger=IntervalTrigger(minutes=5),
            id="news_xueqiu_5m",
            name="雪球 散户讨论",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    except ImportError:
        pass

    # LLM sentiment pipeline (Agent E)
    try:
        from app.services.news.sentiment.scheduler_sentiment import init_sentiment_jobs
        init_sentiment_jobs(scheduler)
    except ImportError:
        pass

    scheduler.start()
    print("[Scheduler] Started")


def shutdown_scheduler():
    """Shut down the background scheduler if it is running."""
    if scheduler.running:
        scheduler.shutdown()
        print("[Scheduler] Shutdown")
