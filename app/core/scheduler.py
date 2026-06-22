"""APScheduler background task scheduler.

Provides scheduled execution of daily ETL, indicator calculation,
scoring, report generation, market scan, and signal generation jobs.
"""

from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.database import SessionLocal
from app.core.redis_client import redis_lock
from app.data.indicators.calculator import batch_calculate_indicators
from app.data.pipelines.a_share import AShareETLPipeline
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
            print("[Scheduler] A-share ETL skipped: daily pipeline lock in use")
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


def run_indicator_calculation(target_date: date | None = None, full_history: bool = False):
    """Run the batch indicator calculation for all active ETFs.

    Args:
        target_date: If provided, calculate indicators up to this date.
        full_history: If True, upsert indicators for every historical trade
            date instead of only the latest day. Useful for backfilling.
    """
    # Wait for the daily ETL lock to be released to avoid calculating
    # indicators while bars are still being written.
    with redis_lock(_LOCK_DAILY_PIPELINE, expire_seconds=3600, wait_timeout=1800) as acquired:
        if not acquired:
            print("[Scheduler] Indicator calculation skipped: could not acquire pipeline lock")
            return

        db = SessionLocal()
        try:
            count = batch_calculate_indicators(
                db, target_date=target_date, full_history=full_history
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
            print("[Scheduler] Score calculation skipped: could not acquire pipeline lock")
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


def run_etf_scan():
    """Run the ETF market scan (Sunday 03:00)."""
    db = SessionLocal()
    try:
        service = ETFScannerService(db)
        result = service.scan_market()
        total = len(result.get("new", [])) + len(result.get("delisted", [])) + len(result.get("changed", []))
        print(f"[Scheduler] ETF scan: {total} changes found")
    finally:
        db.close()


def run_signal_generation(target_date: date | None = None):
    """Generate trading signals for all active strategies (daily 09:00).

    Args:
        target_date: If provided, generate signals for this date instead of today.
    """
    with redis_lock(_LOCK_DAILY_PIPELINE, expire_seconds=1800, wait_timeout=1800) as acquired:
        if not acquired:
            print("[Scheduler] Signal generation skipped: could not acquire pipeline lock")
            return

        db = SessionLocal()
        try:
            strategy_service = StrategyService(db)
            signal_service = SignalService(db)
            strategies = strategy_service.get_strategies()
            active_strategies = [s for s in strategies if s.get("is_active")]

            # Get all active ETFs (previously capped at 50, which contradicted docs).
            etfs = db.query(ETFInfo).filter(ETFInfo.status == "active").all()

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
      - A-share ETL at 15:30 daily
      - Indicator calculation at 08:00 daily
      - Score calculation at 08:30 daily
      - Weekly pool reports on Sunday at 22:00
      - ETF market scan on Sunday at 03:00
      - Signal generation at 09:00 daily
    """
    scheduler.add_job(
        run_a_share_etl,
        trigger=CronTrigger(hour=15, minute=30),
        id="a_share_daily_etl",
        name="A股ETF日终采集",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_indicator_calculation,
        trigger=CronTrigger(hour=8, minute=0),
        id="indicator_calculation",
        name="指标批量计算",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_score_calculation,
        trigger=CronTrigger(hour=8, minute=30),
        id="score_calculation",
        name="评分日终计算",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_weekly_pool_reports,
        trigger=CronTrigger(day_of_week="sun", hour=22, minute=0),
        id="weekly_pool_reports",
        name="池周报生成",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_etf_scan,
        trigger=CronTrigger(day_of_week="sun", hour=3, minute=0),
        id="etf_market_scan",
        name="全市场ETF扫描",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_signal_generation,
        trigger=CronTrigger(hour=9, minute=0),
        id="signal_generation",
        name="交易信号生成",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    print("[Scheduler] Started")


def shutdown_scheduler():
    """Shut down the background scheduler if it is running."""
    if scheduler.running:
        scheduler.shutdown()
        print("[Scheduler] Shutdown")
