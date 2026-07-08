"""APScheduler background task scheduler.

Provides scheduled execution of daily ETL, indicator calculation,
scoring, report generation, market scan, and signal generation jobs.
"""

import json
import logging
from datetime import date, datetime, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.database import SessionLocal
from app.core.redis_client import get_redis_client, redis_lock
from app.data.indicators.calculator import batch_calculate_indicators
from app.data.pipelines.a_share import AShareETLPipeline
from app.data.pipelines.a_share_stock_daily import AStockDailyPipeline
from app.data.pipelines.a_share_stock_discovery import AShareStockDiscoveryPipeline
from app.data.pipelines.a_share_stock_financials import AStockFinancialsPipeline
from app.data.pipelines.a_share_stock_fundamental import AStockFundamentalPipeline
from app.data.pipelines.cninfo_reports import CninfoReportsPipeline
from app.data.pipelines.crypto_daily import CryptoDailyPipeline
from app.data.pipelines.etf_holdings import ETFHoldingsPipeline
from app.data.pipelines.etf_metadata_enrichment import ETFMetadataEnrichmentPipeline
from app.data.pipelines.futures import FuturesContractDiscoveryPipeline, FuturesDailyPipeline
from app.data.pipelines.listing_events import ListingEventsPipeline
from app.data.pipelines.microstructure import MicrostructurePipeline
from app.data.pipelines.research_reports import ResearchReportsPipeline
from app.data.pipelines.search_trends import SearchTrendsPipeline
from app.data.pipelines.sec_edgar import SecEdgarPipeline
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
from app.strategies.base import StrategyRegistry

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


def run_etf_holdings():
    """Run the A-share ETF top-10 holdings pipeline (daily 07:00 Asia/Shanghai).

    Fetches the latest quarterly holdings for every active A-share ETF from
    Akshare (primary) and falls back to Tushare. Existing snapshots are
    replaced per (etf_code, holdings_as_of_date) for idempotency.
    """
    with redis_lock("etf_holdings", expire_seconds=7200) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] ETF holdings skipped: lock in use")
            return
        db = SessionLocal()
        try:
            pipeline = ETFHoldingsPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] ETF holdings: "
                f"success={result.success}, records={result.records}"
            )
        finally:
            db.close()


def run_listing_events():
    """Refresh the listing_events table from Tushare (daily 09:30).

    Free-tier users are gracefully handled: the pipeline falls back to
    stock_basic + 30-day window when ``new_share`` is denied.
    """
    with redis_lock("listing_events_daily", expire_seconds=3600, wait_timeout=600) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Listing events refresh skipped: lock in use")
            return
        db = SessionLocal()
        try:
            pipeline = ListingEventsPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] Listing events refresh: "
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


def run_futures_contract_refresh():
    """Refresh the futures main contract list (monthly day-1 at 03:00)."""
    with redis_lock("futures_contracts_refresh", expire_seconds=3600) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Futures contract refresh skipped: lock in use")
            return
        db = SessionLocal()
        try:
            pipeline = FuturesContractDiscoveryPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] Futures contract refresh: success={result.success}, "
                f"records={result.records}"
            )
        finally:
            db.close()


def run_futures_daily(target_date: date | None = None):
    """Run the futures daily bars ETL pipeline.

    Scheduled at 16:30 Asia/Shanghai — 30 minutes after Chinese commodity
    futures markets close.
    """
    with redis_lock("futures_daily", expire_seconds=3600) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Futures daily skipped: lock in use")
            return
        db = SessionLocal()
        try:
            pipeline = FuturesDailyPipeline(db, target_date=target_date)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] Futures daily (target={target_date}): "
                f"success={result.success}, records={result.records}"
            )
        finally:
            db.close()


def run_sec_edgar_daily():
    """Refresh SEC EDGAR filings (weekly Saturday 06:00 UTC).

    Walks the cached SEC ticker directory in batches (default 50 tickers
    per run) and upserts 10-K / 10-Q / 20-F filings into the
    ``sec_filings`` table.  Best-effort — single ticker failures do not
    abort the batch.
    """
    with redis_lock("sec_edgar_daily", expire_seconds=7200) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] SEC EDGAR refresh skipped: lock in use")
            return
        db = SessionLocal()
        try:
            pipeline = SecEdgarPipeline(db, batch_size=50)
            result = pipeline.run_with_retry(max_attempts=1)
            print(
                f"[Scheduler] SEC EDGAR refresh: "
                f"success={result.success}, records={result.records}"
            )
        finally:
            db.close()


def run_microstructure_daily():
    """Refresh A-share micro-structure tables (daily 18:30 Asia/Shanghai).

    Runs the 4 sub-tasks (LHB / HSGT / margin / restricted) each in
    its own try/except guard — one failure does not abort the others.
    """
    with redis_lock("microstructure_daily", expire_seconds=3600) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Microstructure refresh skipped: lock in use")
            return
        db = SessionLocal()
        try:
            pipeline = MicrostructurePipeline(db)
            result = pipeline.run_with_retry(max_attempts=1)
            print(
                f"[Scheduler] Microstructure refresh: "
                f"success={result.success}, records={result.records}"
            )
        finally:
            db.close()


def run_search_trends_daily():
    """Refresh Baidu + Google search-trend observations (daily 03:00 Asia/Shanghai).

    Pulls one observation per (rotated) keyword for each source and
    upserts into the ``search_trends`` table.  Google keywords each
    block ~60s due to pytrends rate limiting.
    """
    with redis_lock("search_trends_daily", expire_seconds=1800) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Search trends refresh skipped: lock in use")
            return
        db = SessionLocal()
        try:
            pipeline = SearchTrendsPipeline(db)
            result = pipeline.run_with_retry(max_attempts=1)
            print(
                f"[Scheduler] Search trends refresh: "
                f"success={result.success}, records={result.records}"
            )
        finally:
            db.close()


def run_china_macro_refresh():
    """Refresh China macro indicators (akshare).

    Pulls GDP / CPI / PPI / M2 / PMI / SHIBOR / RRR from akshare's
    ``macro_china_*`` family and upserts into the macro_indicator table.
    Best-effort: per-series failures are logged inside
    ``run_china_macro_refresh`` and never crash the scheduler.
    """
    from app.services.macro.scheduler import run_china_macro_refresh as _run

    with redis_lock("china_macro_daily", expire_seconds=3600) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] China macro refresh skipped: lock in use")
            return
        try:
            result = _run()
            print(
                f"[Scheduler] China macro refresh: written={result.get('written', 0)}, "
                f"fetched={result.get('fetched', 0)}, "
                f"failed={result.get('failed', [])}"
            )
        except Exception as exc:  # pragma: no cover - last-resort guard
            print(f"[Scheduler] China macro refresh crashed: {exc}")


def run_global_indices_refresh():
    """Refresh global market indices (Phase 5d).

    Pulls Hang Seng / Nikkei / DAX / FTSE / CAC / ASX / KOSPI / TWSE
    / NIFTY / SENSEX via yfinance and 上证综指 / 深证成指 / 沪深300 via
    akshare, then upserts every observation into the ``macro_indicator``
    table tagged with ``region='global'``.  Best-effort: per-ticker
    failures are logged inside ``run_global_indices_refresh`` and
    never crash the scheduler.

    Runs daily at 16:00 Asia/Shanghai — 1 hour after Asia close so
    that the most recent Hong Kong / Japan / Australia / A-share
    closes are settled.
    """
    from app.services.macro.global_indices_fetcher import (
        run_global_indices_refresh as _run,
    )

    with redis_lock("global_indices_daily", expire_seconds=3600) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Global indices refresh skipped: lock in use")
            return
        try:
            result = _run()
            print(
                f"[Scheduler] Global indices refresh: "
                f"written={result.get('written', 0)}, "
                f"fetched={result.get('fetched', 0)}, "
                f"failed={result.get('failed', [])}, "
                f"per_source={result.get('per_source', {})}"
            )
        except Exception as exc:  # pragma: no cover - last-resort guard
            print(f"[Scheduler] Global indices refresh crashed: {exc}")


def run_research_reports_daily():
    """Refresh research_reports (daily 18:00 Asia/Shanghai).

    Walks active A-share individual stocks, fetches recent analyst
    reports from Eastmoney (via akshare), and upserts them into the
    ``research_reports`` table. Safe to re-run thanks to the unique
    constraint on ``(ts_code, title, publish_date)``.
    """
    from app.data.pipelines.research_reports import ResearchReportsPipeline

    with redis_lock("research_reports_daily", expire_seconds=3600) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Research-reports refresh skipped: lock in use")
            return
        db = SessionLocal()
        try:
            pipeline = ResearchReportsPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] Research-reports daily: "
                f"success={result.success}, records={result.records}"
            )
        finally:
            db.close()


def run_summarize_pending_reports():
    """DeepSeek-summarize up to 20 unsummarized reports (every 2h).

    Idempotent: only touches rows where ``summary IS NULL``. Rows that
    fail (timeout / 429 / no API key) are left for the next run.
    """
    from app.services.research_report_service import ResearchReportService

    with redis_lock("research_reports_summarize", expire_seconds=1800) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Research-reports summarize skipped: lock in use")
            return
        db = SessionLocal()
        try:
            service = ResearchReportService(db)
            count = service.summarize_pending_reports(batch_size=20, max_per_run=20)
            print(f"[Scheduler] Research-reports summarize: {count} summarized")
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

        # Get all active instruments (ETFs, stocks, crypto).
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
            etf_codes = [e.code for e in etfs]

            for strategy in active_strategies:
                strategy_type = strategy["strategy_type"]
                params = strategy["params"]
                strategy_id = strategy["id"]

                strategy_class = StrategyRegistry.get(strategy_type)
                is_cross_sectional = (
                    strategy_class is not None and strategy_class.family == "cross_sectional"
                )

                try:
                    if is_cross_sectional:
                        signals = signal_service.generate_signals_universe(
                            strategy_id=strategy_id,
                            etf_codes=etf_codes,
                            strategy_type=strategy_type,
                            params=params,
                            trade_date=trade_date,
                        )
                        total_signals += len(signals)
                    else:
                        for etf in etfs:
                            try:
                                signals = signal_service.generate_signals(
                                    strategy_id=strategy_id,
                                    etf_code=etf.code,
                                    strategy_type=strategy_type,
                                    params=params,
                                    trade_date=trade_date,
                                )
                                total_signals += len(signals)
                            except Exception as e:
                                print(f"[Scheduler] Signal generation failed for {etf.code}: {e}")
                except Exception as e:
                    print(f"[Scheduler] Signal generation failed for strategy {strategy_id}: {e}")

            print(f"[Scheduler] Signal generation (target={target_date}): {total_signals} signals generated")
        finally:
            db.close()


def run_cninfo_reports_daily():
    """Refresh cninfo periodic reports (daily 17:00 Asia/Shanghai).

    Walks the HS300 + CS500 universe (B-tier) and pulls the four
    periodic-report categories published in the last 7 days.  Safe to
    re-run thanks to the unique constraint on ``announcement_id``.
    """
    with redis_lock("cninfo_reports_daily", expire_seconds=3600, wait_timeout=600) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Cninfo reports refresh skipped: lock in use")
            return
        db = SessionLocal()
        try:
            pipeline = CninfoReportsPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] Cninfo reports daily: "
                f"success={result.success}, records={result.records}"
            )
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
      - A-share ETF holdings at 07:00 daily
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
      - Futures daily ETL at 16:30 daily
      - Futures contract refresh on day-1 at 03:00 monthly
      - Research reports daily ETL at 18:00 daily
      - Research report DeepSeek summarization every 2 hours
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
    scheduler.add_job(
        run_etf_holdings,
        trigger=CronTrigger(hour=7, minute=0, timezone="Asia/Shanghai"),
        id="etf_holdings",
        name="A股ETF前十大持仓采集",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_listing_events,
        trigger=CronTrigger(hour=9, minute=30, timezone="Asia/Shanghai"),
        id="listing_events_daily",
        name="上市预告日刷",
        replace_existing=True,
        max_instances=1,
    )
    # ── Cninfo Periodic Reports ──
    scheduler.add_job(
        run_cninfo_reports_daily,
        trigger=CronTrigger(hour=17, minute=0, timezone="Asia/Shanghai"),
        id="cninfo_reports_daily",
        name="巨潮定期报告日刷",
        replace_existing=True,
        max_instances=1,
    )
    # ── Macro Jobs ──
    scheduler.add_job(
        run_china_macro_refresh,
        trigger=CronTrigger(
            hour=9, minute=30, day_of_week="mon-fri", timezone="Asia/Shanghai"
        ),
        id="china_macro_daily",
        name="中国宏观日刷",
        replace_existing=True,
        max_instances=1,
    )
    # ── Global Market Indices (yfinance + akshare) ──
    # 16:00 Asia/Shanghai = 1 hour after Asia close so HK / JP / AU /
    # A-share closes are settled.  Mon-Fri only — equities are closed
    # on weekends; Saturday / Sunday snapshots from upstream would be
    # Friday's close repeated.
    scheduler.add_job(
        run_global_indices_refresh,
        trigger=CronTrigger(
            hour=16, minute=0, day_of_week="mon-fri", timezone="Asia/Shanghai"
        ),
        id="global_indices_daily",
        name="全球主要指数日刷",
        replace_existing=True,
        max_instances=1,
    )
    # ── Futures Jobs ──
    scheduler.add_job(
        run_futures_daily,
        trigger=CronTrigger(hour=16, minute=30, timezone="Asia/Shanghai"),
        id="futures_daily_etl",
        name="国内期货日终采集",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_futures_contract_refresh,
        trigger=CronTrigger(
            day=1, hour=3, minute=0, timezone="Asia/Shanghai"
        ),
        id="futures_contracts_refresh",
        name="国内期货主力合约刷新",
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

    # ── ETF Holdings Quarterly (Phase 9b) ──
    # Three cron jobs in the seasonal disclosure windows (Q1 / mid-year /
    # Q3) that fire a deterministic catch-up refresh of the top-10
    # holdings table.  Complements the daily 07:00 opportunistic
    # ``etf_holdings`` job above.  See
    # ``app.scheduler_jobs.etf_holdings_quarterly`` for details.
    try:
        from app.scheduler_jobs.etf_holdings_quarterly import (
            register as register_etf_holdings_quarterly,
        )

        register_etf_holdings_quarterly(scheduler)
    except ImportError:
        pass
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
    # ── Research Reports ──
    scheduler.add_job(
        run_research_reports_daily,
        trigger=CronTrigger(hour=18, minute=0, timezone="Asia/Shanghai"),
        id="research_reports_daily",
        name="A股研报日抓取",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_summarize_pending_reports,
        trigger=IntervalTrigger(hours=2),
        id="research_summarize",
        name="研报 DeepSeek 摘要补齐",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    # ── Macro (FRED) — daily after FRED publishes (~15:00 ET)
    try:
        from app.services.news.scheduler_jobs import run_fred_refresh
        from app.core.redis_client import redis_lock

        def _fred_wrapper():
            with redis_lock("fred_macro_daily", expire_seconds=1800) as acquired:
                if not acquired:
                    print("⚠️ [SCHEDULER_WARN] FRED refresh skipped: lock in use")
                    return
                run_fred_refresh()

        # 15:00 ET ≈ 03:00 Beijing time next day (EDT) / 04:00 (EST).
        # day_of_week='mon-fri' — FRED doesn't publish on weekends.
        scheduler.add_job(
            _fred_wrapper,
            trigger=CronTrigger(
                hour=3, minute=0, day_of_week="mon-fri", timezone="Asia/Shanghai"
            ),
            id="fred_macro_daily",
            name="FRED 美国宏观日刷",
            replace_existing=True,
            max_instances=1,
        )
    except ImportError:
        pass

    # ── News / Sentiment Jobs ──
    # A-share RSS feeds (every 5 minutes)
    # NOTE: xinhua RSS endpoints are currently 404; disabled to avoid log spam.
    try:
        from app.services.news.scheduler_jobs import (
            run_cninfo_crawl, run_sina_crawl,
            run_wechat_zeping_crawl,
            run_yahoo_crawl, run_cnbc_crawl, run_sec_edgar_crawl,
            run_reddit_crawl,
            run_coindesk_crawl, run_cointelegraph_crawl,
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
            run_wechat_zeping_crawl,
            trigger=IntervalTrigger(minutes=15),
            id="news_wechat_zeping_15m",
            name="微信公众号 (wewe-rss)",
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
        scheduler.add_job(
            run_coindesk_crawl,
            trigger=IntervalTrigger(minutes=5),
            id="news_coindesk_5m",
            name="CoinDesk RSS",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_cointelegraph_crawl,
            trigger=IntervalTrigger(minutes=5),
            id="news_cointelegraph_5m",
            name="Cointelegraph RSS",
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

    # News full content fetcher (runs after xueqiu crawler, every 10 minutes)
    try:
        from app.services.news.scheduler_fetch_full_content import run_fetch_full_content
        scheduler.add_job(
            run_fetch_full_content,
            trigger=IntervalTrigger(minutes=10),
            id="news_full_content_10m",
            name="资讯全文抓取",
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

    # ── SEC EDGAR (Phase 6) ── weekly Saturday 06:00 UTC
    scheduler.add_job(
        run_sec_edgar_daily,
        trigger=CronTrigger(
            day_of_week="sat", hour=6, minute=0, timezone="UTC"
        ),
        id="sec_edgar_daily",
        name="SEC EDGAR 周报采集",
        replace_existing=True,
        max_instances=1,
    )
    # ── Microstructure (Phase 7) ── daily 18:30 Asia/Shanghai
    scheduler.add_job(
        run_microstructure_daily,
        trigger=CronTrigger(hour=18, minute=30, timezone="Asia/Shanghai"),
        id="microstructure_daily",
        name="A 股微结构数据日刷",
        replace_existing=True,
        max_instances=1,
    )
    # ── Search Trends (Phase 9) ── daily 03:00 Asia/Shanghai
    scheduler.add_job(
        run_search_trends_daily,
        trigger=CronTrigger(hour=3, minute=0, timezone="Asia/Shanghai"),
        id="search_trends_daily",
        name="搜索热度日刷",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.add_job(
        _scheduler_heartbeat,
        trigger=IntervalTrigger(minutes=1),
        id="scheduler_heartbeat",
        name="调度器心跳",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler_heartbeat()
    scheduler.start()
    print("[Scheduler] Started")


def shutdown_scheduler():
    """Shut down the background scheduler if it is running."""
    if scheduler.running:
        scheduler.shutdown()
        print("[Scheduler] Shutdown")


_SCHEDULER_HEARTBEAT_KEY = "ad_research:scheduler:heartbeat"
_SCHEDULER_JOBS_KEY = "ad_research:scheduler:jobs"
_SCHEDULER_HEARTBEAT_TTL_SECONDS = 180


def _scheduler_heartbeat():
    """Emit a Redis heartbeat and persist the job list for cross-worker visibility.

    APScheduler's BackgroundScheduler is per-process. In a multi-worker
    deployment only the leader worker has jobs registered; this heartbeat
    lets every worker report scheduler liveness and the current schedule.
    """
    try:
        client = get_redis_client()
        now = datetime.now(timezone.utc).isoformat()
        jobs: list[dict[str, Any]] = []
        if scheduler.running:
            for job in scheduler.get_jobs():
                next_run = job.next_run_time
                jobs.append(
                    {
                        "id": job.id,
                        "name": getattr(job, "name", None) or job.id,
                        "next_run_time": next_run.isoformat() if next_run else None,
                    }
                )
        client.setex(
            _SCHEDULER_HEARTBEAT_KEY,
            _SCHEDULER_HEARTBEAT_TTL_SECONDS,
            now,
        )
        if jobs:
            client.setex(
                _SCHEDULER_JOBS_KEY,
                _SCHEDULER_HEARTBEAT_TTL_SECONDS,
                json.dumps(jobs),
            )
    except Exception:
        logging.getLogger(__name__).exception("Scheduler heartbeat failed")


def is_scheduler_running() -> bool:
    """Return True if the scheduler leader is alive.

    Uses a Redis heartbeat so non-leader workers can report the same state
    as the worker actually running the jobs.
    """
    if scheduler.running:
        return True
    try:
        client = get_redis_client()
        return client.exists(_SCHEDULER_HEARTBEAT_KEY) > 0
    except Exception:  # pragma: no cover - defensive
        return False


def get_scheduler_jobs() -> list[dict[str, Any]]:
    """Introspect scheduled jobs, falling back to the leader's Redis snapshot.

    Returns a JSON-safe list of job metadata. Safe to call even when the
    local scheduler has not been started.
    """
    try:
        client = get_redis_client()
        payload = client.get(_SCHEDULER_JOBS_KEY)
        if payload:
            return json.loads(payload)
    except Exception:
        logging.getLogger(__name__).exception("Failed to load scheduler jobs from Redis")

    if not scheduler.running:
        return []
    out: list[dict[str, Any]] = []
    try:
        for job in scheduler.get_jobs():
            next_run = job.next_run_time
            out.append(
                {
                    "id": job.id,
                    "name": getattr(job, "name", None) or job.id,
                    "next_run_time": next_run.isoformat() if next_run else None,
                }
            )
    except Exception:  # pragma: no cover - defensive
        return out
    return out
