"""APScheduler background task scheduler.

Provides scheduled execution of daily ETL, indicator calculation,
scoring, report generation, market scan, and signal generation jobs.
"""

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.core.redis_client import get_redis_client, redis_lock
from app.tasks.cninfo import refresh_cninfo_reports_daily
from app.tasks.indicator import calculate_indicators
from app.data.pipelines.a_share import AShareETLPipeline
from app.data.pipelines.a_share_stock_daily import AStockDailyPipeline
from app.data.pipelines.a_share_stock_discovery import AShareStockDiscoveryPipeline
from app.data.pipelines.a_share_stock_financials import AStockFinancialsPipeline
from app.data.pipelines.a_share_stock_fundamental import AStockFundamentalPipeline
from app.data.pipelines.crypto_daily import CryptoDailyPipeline
from app.data.pipelines.etf_holdings import ETFHoldingsPipeline
from app.scripts.backfill_a_share_adj_factor import backfill_adj_factor
from app.data.pipelines.etf_metadata_enrichment import ETFMetadataEnrichmentPipeline
from app.data.pipelines.futures import FuturesContractDiscoveryPipeline, FuturesDailyPipeline
from app.data.pipelines.fund_flow import FundFlowPipeline
from app.data.pipelines.listing_events import ListingEventsPipeline
from app.data.pipelines.market_fund_flow import MarketFundFlowPipeline
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
from app.models.etl import ETLLog, StrategyConfig
from app.models.pool import ETFPools
from app.models.user import User
from app.services.etf_scanner_service import ETFScannerService
from app.services.report_service import ReportService
from app.services.scoring_service import ScoringService
from app.services.signal_service import SignalService
from app.strategies.base import StrategyRegistry

# Limit the default APScheduler thread pool. The default 20 workers can
# launch too many long-running DB-holding jobs concurrently and exhaust the
# backend connection pool (Action-253 follow-up). 5 concurrent scheduler
# jobs is enough for our nightly batch while leaving headroom for the API.
scheduler = BackgroundScheduler(executors={"default": ThreadPoolExecutor(max_workers=5)})

# Names for distributed locks used by scheduled jobs.
_LOCK_ETL = "daily_etl"
_LOCK_DAILY_PIPELINE = "daily_pipeline"

# Running ETL jobs older than this are considered stuck and will be cleaned
# up before the next scheduled run (see ``cleanup_stuck_etl_jobs``).
_STUCK_ETL_THRESHOLD_MINUTES = 120

# 2026-07-19：磁盘监控阈值（/data 实际容量 118GB / resize2fs 后）。
# 2026-07-17 /data 100% 触发 Redis 写失败 / health degraded（见 20260717-disk-full
# runbook），但当时 /data 仅 40GB，现在已扩到 120GB。阈值按新容量重配：
#   - 80% warn  → 96GB  → 提醒人工清理
#   - 95% error → 114GB → 强烈建议立刻清理，否则会撞 2026-07-17 同样的故障
# 旧 memory 里"40GB / 80% 阈值"已过期，这里以新容量为基准。
_DISK_WARN_RATIO = 0.80
_DISK_ERROR_RATIO = 0.95
_DISK_PATHS = ("/data", "/")


# Maps ETLLog.job_name -> Redis lock name(s) used by the scheduler.
# Keep this in sync with the lock names used in each run_* function below.
_ETL_JOB_LOCK_MAP: dict[str, str | list[str]] = {
    "a_share_daily_etl": "daily_pipeline",
    "a_stock_daily_etl": "a_stock_daily_pipeline",
    "a_share_fundamental_etl": "a_stock_fundamental_pipeline",
    "a_share_discovery_etl": "a_stock_discovery",
    "a_share_financials_etl": "a_stock_financials",
    "a_share_adj_factor_backfill": "a_share_adj_factor_backfill",
    "us_daily_etl": "us_daily_pipeline",
    "us_historical_backfill": "us_backfill_pipeline",
    "us_etf_discovery": "us_etf_discovery",
    "us_stock_discovery": "us_stock_discovery",
    "us_stock_enrichment": "us_stock_enrichment",
    "crypto_daily_etl": "crypto_daily_pipeline",
    "weekly_pool_reports": "weekly_pool_reports",
    "sw_industry_index_refresh": "sw_industry_index_refresh",
    "etf_scan": "etf_scan",
    "etf_metadata_enrichment": "etf_metadata_enrichment",
    "etf_holdings": "etf_holdings",
    "listing_events_daily": "listing_events_daily",
    "futures_contracts_refresh": "futures_contracts_refresh",
    "futures_daily": "futures_daily",
    "sec_edgar_daily": "sec_edgar_daily",
    "microstructure_daily": "microstructure_daily",
    "fund_flow_daily": "fund_flow_daily",
    "market_fund_flow_daily": "market_fund_flow_daily",
    "research_reports_daily": "research_reports_daily",
    "search_trends_daily": "search_trends_daily",
    "china_macro_daily": "china_macro_daily",
    "global_indices_daily": "global_indices_daily",
    "cninfo_reports_daily": "cninfo_reports_daily",
}


def _resolve_a_share_target_date(
    target_date: date | None,
    db: Any,
) -> date | None:
    """解析显式 target_date，未传入时从 A 股最新 bar 推断。

    查询 ``instrument_daily_bar`` 表中 ``market='A股'`` 的最大
    ``trade_date``，避免调度器在 bars 未落地时发起空跑任务。

    当最新 bar 明显滞后（>2 个交易日）时打印告警，便于运维在数据
    停滞时第一时间发现，而不是等到下游指标/评分缺失才排查。
    """
    if target_date is not None:
        return target_date

    from app.models.etf import ETFInfo, InstrumentDailyBar

    row = (
        db.query(InstrumentDailyBar.trade_date)
        .join(ETFInfo, ETFInfo.code == InstrumentDailyBar.etf_code)
        .filter(ETFInfo.market == "A股")
        .order_by(InstrumentDailyBar.trade_date.desc())
        .first()
    )
    latest = row[0] if row else None
    if latest is not None:
        today = date.today()
        lag = (today - latest).days
        # 简单 heuristic：非周五时滞后 >2 个自然日即告警
        if lag > 2:
            logger = logging.getLogger(__name__)
            logger.warning(
                "A-share latest bar %s is %d calendar day(s) behind today %s; "
                "indicator calc may operate on stale data",
                latest,
                lag,
                today,
            )
    return latest


def _acquire_indicator_date_lock(target_date: date, full_history: bool) -> bool:
    """以日期维度获取 Redis 锁，防止同一日期的指标任务被重复调度。

    锁的 TTL 设为 12 小时，覆盖指标任务最长运行时间；任务完成后即使未主动
    释放，也会在下一个交易日自动过期。
    """
    client = get_redis_client()
    lock_key = (
        f"ad_research:indicator:a_share:{target_date.isoformat()}"
        f":fh={full_history}"
    )
    return client.set(lock_key, "1", nx=True, ex=12 * 3600) is True


def _lock_names_for_job(job_name: str) -> list[str]:
    """Return Redis lock name(s) that may belong to a given ETL job."""
    mapped = _ETL_JOB_LOCK_MAP.get(job_name)
    names: list[str] = []
    if mapped:
        if isinstance(mapped, list):
            names.extend(mapped)
        else:
            names.append(mapped)
    if job_name not in names:
        names.append(job_name)
    return names


def cleanup_stuck_etl_jobs(threshold_minutes: int = _STUCK_ETL_THRESHOLD_MINUTES) -> int:
    """Clean up ETL jobs stuck in the ``running`` state.

    When a container is SIGKILLed or a process dies without updating its
    ``ETLLog`` row, the record stays ``running`` and the Redis lock may still
    be held.  This function marks those rows as ``failed`` and deletes the
    associated Redis locks so the next scheduled run is not blocked.

    Returns the number of stuck rows cleaned up.
    """
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)
    cleaned = 0

    with SessionLocal() as db:
        stuck_logs = (
            db.query(ETLLog)
            .filter(ETLLog.status == "running")
            .filter(ETLLog.start_time < cutoff)
            .order_by(ETLLog.start_time.asc())
            .all()
        )

        if not stuck_logs:
            return 0

        logger = logging.getLogger(__name__)
        logger.warning(
            "Found %d stuck ETL job(s) older than %d minutes",
            len(stuck_logs),
            threshold_minutes,
        )

        client = get_redis_client()
        for log in stuck_logs:
            job_name = log.job_name or "unknown"
            start = log.start_time.isoformat() if log.start_time else "?"
            logger.info("Cleaning up stuck ETL job %s (started %s)", job_name, start)

            log.status = "failed"
            log.end_time = datetime.now(timezone.utc)
            log.error_msg = (
                (log.error_msg or "")
                + "; [scheduler-cleanup] process terminated or lease expired"
            )
            cleaned += 1

            for lock_name in _lock_names_for_job(job_name):
                lock_key = f"lock:{lock_name}"
                try:
                    if client.delete(lock_key):
                        logger.info("Released Redis lock %s", lock_key)
                except Exception:
                    logger.exception("Failed to delete Redis lock %s", lock_key)

        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to commit stuck-ETL cleanup")
            raise

    return cleaned


def check_disk_usage() -> dict[str, dict[str, float]]:
    """检查 /data 与 / 的磁盘使用率，超阈值打 warning/error 日志。

    2026-07-17 /data 100% 触发 Redis 写失败 + /health degraded (见
    20260717-disk-full-redis-write-error.md)；当时 /data 仅 40GB，
    现已 resize2fs 到 118GB。本函数作为低成本兜底：每小时由 scheduler
    触发，超阈值打日志（warn = 80%, error = 95%），便于运维提前干预。
    没接 Prometheus / Grafana — 项目目前没有集中监控；日志路径走
    docker compose logs backend 即可检索。

    Returns:
        每路径一个 dict: ``{path: {"total_gb", "used_gb", "free_gb", "ratio"}}``，
        便于后续接 API 暴露或写 JSON 指标文件。
    """
    import shutil

    logger = logging.getLogger(__name__)
    out: dict[str, dict[str, float]] = {}
    for path in _DISK_PATHS:
        if not Path(path).exists():
            continue
        try:
            usage = shutil.disk_usage(path)
        except Exception:
            logger.exception("disk_usage check failed for %s", path)
            continue
        total_gb = usage.total / (1024 ** 3)
        used_gb = usage.used / (1024 ** 3)
        free_gb = usage.free / (1024 ** 3)
        ratio = usage.used / usage.total if usage.total else 0.0
        out[path] = {
            "total_gb": round(total_gb, 2),
            "used_gb": round(used_gb, 2),
            "free_gb": round(free_gb, 2),
            "ratio": round(ratio, 4),
        }
        if ratio >= _DISK_ERROR_RATIO:
            logger.error(
                "[disk] %s 已用 %.1f%% (%.1f/%.1f GB)，超过 error 阈值 %.0f%%，"
                "请立即清理（参考 docs/dev-notes/20260717-disk-full-redis-write-error.md）",
                path, ratio * 100, used_gb, total_gb, _DISK_ERROR_RATIO * 100,
            )
        elif ratio >= _DISK_WARN_RATIO:
            logger.warning(
                "[disk] %s 已用 %.1f%% (%.1f/%.1f GB)，超过 warn 阈值 %.0f%%，"
                "建议尽快清理",
                path, ratio * 100, used_gb, total_gb, _DISK_WARN_RATIO * 100,
            )
        else:
            logger.debug("[disk] %s 已用 %.1f%% (%.1f/%.1f GB)", path, ratio * 100, used_gb, total_gb)
    return out


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

        with SessionLocal() as db:
            pipeline = AShareETLPipeline(db, target_date=target_date, prefer_sina=prefer_sina)
            result = pipeline.run_with_retry(max_attempts=3)
            print(
                f"[Scheduler] A-share ETL (target={target_date}, sina={prefer_sina}): success={result.success}, records={result.records}"
            )


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

        with SessionLocal() as db:
            pipeline = AStockDailyPipeline(db, target_date=target_date)
            result = pipeline.run_with_retry(max_attempts=3)
            print(
                f"[Scheduler] A-stock daily ETL (target={target_date}): "
                f"success={result.success}, records={result.records}"
            )


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

        with SessionLocal() as db:
            pipeline = AStockFundamentalPipeline(db, target_date=target_date)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] A-stock fundamental ETL (target={target_date}): "
                f"success={result.success}, records={result.records}"
            )


def run_a_share_stock_discovery():
    """Run the A-share individual stock discovery pipeline (weekly Monday 01:00).

    Fetches the full A-share stock list from Tushare stock_basic across
    SSE, SZSE, and BSE, and upserts into etf_info.
    """
    with redis_lock("a_stock_discovery", expire_seconds=7200) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] A-share stock discovery skipped: lock in use")
            return
        with SessionLocal() as db:
            pipeline = AShareStockDiscoveryPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] A-share stock discovery: "
                f"success={result.success}, records={result.records}"
            )


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
        with SessionLocal() as db:
            pipeline = AStockFinancialsPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] A-share stock financials: "
                f"success={result.success}, records={result.records}"
            )


def run_a_share_adj_factor_backfill():
    """Weekly full-history backfill of A-share adj_factor from Tushare.

    Runs every Sunday at 03:30 Asia/Shanghai. For each active A-share
    instrument the script fetches the cumulative adjustment factor over the
    full range of locally stored daily bars, upserts the result into
    ``adj_factor_history``, and mirrors the values back to
    ``instrument_daily_bar.adj_factor`` for backwards compatibility.

    After this job completes, run ``recalc_a_share_indicators.py`` (or the
    daily 08:00/17:00 indicator calculation) to recompute A-share indicators
    on the corrected dividend-adjusted close.
    """
    lock_name = "a_share_adj_factor_backfill"
    with redis_lock(lock_name, expire_seconds=14400) as acquired:
        if not acquired:
            print(
                "⚠️ [SCHEDULER_WARN] A-share adj_factor backfill skipped: lock in use"
            )
            return

        with SessionLocal() as db:
            result = backfill_adj_factor(
                db,
                codes=None,
                update_daily_bar=True,
                dry_run=False,
                chunk_size=5000,
            )
            print(
                f"[Scheduler] A-share adj_factor backfill: "
                f"history={result['adj_factor_history_records']}, "
                f"daily_bar_updated={result['daily_bar_updated']}, "
                f"errors={result['errors']}"
            )


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

        with SessionLocal() as db:
            pipeline = USDailyPipeline(db, target_date=target_date)
            result = pipeline.run_with_retry(max_attempts=3)
            print(
                f"[Scheduler] US ETL (target={target_date}): "
                f"success={result.success}, records={result.records}"
            )


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

        with SessionLocal() as db:
            pipeline = USHistoricalBackfillPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] US historical backfill: "
                f"success={result.success}, records={result.records}"
            )


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

        calculate_indicators.delay(
            target_date=target_date.isoformat() if target_date else None,
            full_history=False,
            market_filter="US",
        )
        print(f"[Scheduler] US indicator calculation task submitted (target={target_date})")


def run_indicator_calculation(target_date: date | None = None, full_history: bool = False):
    """Run the batch indicator calculation for A-share instruments.

    US and Crypto instruments have their own indicator calculation jobs
    (run_us_indicator_calculation, run_crypto_indicator_calculation) that
    run immediately after their respective ETL pipelines.

    The ``market_filter='A股'`` path inside ``batch_calculate_indicators``
    covers **all** active A-share instruments — both ETFs
    (``instrument_type='ETF'``) and individual stocks
    (``instrument_type='STOCK'``). It does NOT filter on ``instrument_type``,
    so a single call processes ~7 100 codes. The A-share daily-bar ETL,
    however, is split across two pipelines that fetch from different
    providers:

    * ``AShareETLPipeline`` (akshare) — only ``instrument_type == 'ETF'``
      — runs daily at 15:30 Asia/Shanghai.
    * ``AStockDailyPipeline`` (tushare) — only ``instrument_type == 'STOCK'``
      — runs daily at 16:00 Asia/Shanghai.

    When one of those two pipelines fails on a given day (transient
    upstream errors, type-cast failures, etc.) the corresponding
    ``instrument_daily_bar`` rows never land and the indicator calc on
    the next morning only sees half the universe. The companion
    ``run_a_share_indicator_fallback`` cron below re-runs the calc at
    17:00 — after both ETLs have finished and any retries inside
    ``run_with_retry`` have completed — to cover anything the 08:00
    run missed.

    Args:
        target_date: If provided, calculate indicators up to this date.
        full_history: If True, upsert indicators for every historical trade
            date instead of only the latest day. Useful for backfilling.
    """
    # Resolve target_date first: explicit value takes precedence; otherwise
    # infer from the latest A-share bar in instrument_daily_bar.
    with SessionLocal() as db:
        effective_date = _resolve_a_share_target_date(target_date, db)
        if effective_date is None:
            print(
                "⚠️ [SCHEDULER_WARN] A-share indicator calculation skipped: "
                "no A-share bars found"
            )
            return

    # Wait for the daily ETL lock to be released to avoid calculating
    # indicators while bars are still being written.
    with redis_lock(_LOCK_DAILY_PIPELINE, expire_seconds=3600, wait_timeout=1800) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Indicator calculation skipped: could not acquire pipeline lock")
            return

        # Avoid duplicate dispatch for the same date (08:00 main run vs 17:00 fallback).
        if not _acquire_indicator_date_lock(effective_date, full_history):
            print(
                f"⚠️ [SCHEDULER_WARN] A-share indicator calculation skipped: "
                f"task for {effective_date} (full_history={full_history}) is already running or reserved"
            )
            return

        calculate_indicators.delay(
            target_date=effective_date.isoformat(),
            full_history=full_history,
            market_filter="A股",
        )
        print(
            f"[Scheduler] A-share indicator calculation task submitted "
            f"(target={effective_date}, full_history={full_history})"
        )


def run_a_share_indicator_fallback(target_date: date | None = None):
    """Defensive 17:00 re-run of A-share indicator calculation.

    The 08:00 cron entry for ``run_indicator_calculation`` runs *before*
    the 16:00 A-share stock daily-bar ETL, so on days when either of the
    two daily-bar pipelines (ETF at 15:30, STOCK at 16:00) fails or
    retries into the late afternoon, the morning indicator calc only
    sees half the universe and writes either ETF-only or STOCK-only
    records for that trade date.

    This fallback fires at 17:00 Asia/Shanghai — 1 hour after the stock
    ETL completes and after the microstructure (18:30) and the
    fundamentals (16:30) runs — and re-submits the same
    ``market_filter='A股'`` task so whatever bars are in
    ``instrument_daily_bar`` by 17:00 (both ETF and STOCK, assuming
    both ETLs finished) get processed into the ``etf_indicator`` table.

    The Celery task is idempotent: ``on_conflict_do_update`` upserts by
    (etf_code, trade_date), so a second run on the same trade date
    simply overwrites stale values without duplicating rows. A no-op
    (no new bars) is cheap (~10 s of SELECT-then-empty-UPSERT).

    Args:
        target_date: If provided, calculate indicators up to this date.
    """
    # Resolve target_date first: explicit value takes precedence; otherwise
    # infer from the latest A-share bar in instrument_daily_bar.
    with SessionLocal() as db:
        effective_date = _resolve_a_share_target_date(target_date, db)
        if effective_date is None:
            print(
                "⚠️ [SCHEDULER_WARN] A-share indicator fallback skipped: "
                "no A-share bars found"
            )
            return

    # Wait for the daily ETL lock to be released (covers any
    # ``run_with_retry`` still chewing on the 15:30 / 16:00 ETL).
    with redis_lock(_LOCK_DAILY_PIPELINE, expire_seconds=3600, wait_timeout=1800) as acquired:
        if not acquired:
            print(
                "⚠️ [SCHEDULER_WARN] A-share indicator fallback skipped: "
                "could not acquire pipeline lock"
            )
            return

        # Avoid duplicate dispatch for the same date (17:00 fallback vs 08:00 main run).
        if not _acquire_indicator_date_lock(effective_date, False):
            print(
                f"⚠️ [SCHEDULER_WARN] A-share indicator fallback skipped: "
                f"task for {effective_date} is already running or reserved"
            )
            return

        calculate_indicators.delay(
            target_date=effective_date.isoformat(),
            full_history=False,
            market_filter="A股",
        )
        print(
            f"[Scheduler] A-share indicator fallback task submitted "
            f"(target={effective_date})"
        )


def run_score_calculation(target_date: date | None = None):
    """Run the daily ETF composite score calculation for all templates.

    Args:
        target_date: If provided, calculate scores for this date.
    """
    with redis_lock(_LOCK_DAILY_PIPELINE, expire_seconds=1800, wait_timeout=1800) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Score calculation skipped: could not acquire pipeline lock")
            return

        with SessionLocal() as db:
            service = ScoringService(db)
            results = service.calculate_daily_scores(trade_date=target_date)
            total = sum(results.values())
            print(f"[Scheduler] Score calculation (target={target_date}): {total} scores across {len(results)} templates")


def run_sw_industry_index_refresh():
    """Refresh SW2021 一级行业指数回报 (Phase 3 sector rotation 数据源)。

    调度：每周一 09:30 Asia/Shanghai（盘前完成，覆盖到周一开盘用户）。
    通过 Celery 投递到 ``industry`` 队列，由 celery-worker-cninfo
    消费（队列默认并发 2，足够 31 个指数的 AKShare 拉取）。
    """
    from app.tasks.sw_industry import refresh_sw_industry_returns

    with redis_lock("sw_industry_index_refresh", expire_seconds=1800) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] SW industry index refresh skipped: lock in use")
            return
        result = refresh_sw_industry_returns.delay(lookback_days=400)
        print(f"[Scheduler] SW industry index refresh dispatched: task_id={result.id}")


def run_weekly_pool_reports():
    """Generate weekly reports for all ETF pools (Sunday 22:00)."""
    with redis_lock("weekly_pool_reports", expire_seconds=3600) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Weekly pool reports skipped: lock in use")
            return
        # Fetch the pool list in a short session; each report gets its own
        # session so a long-running report does not hold a connection while
        # other reports are being generated.
        with SessionLocal() as db:
            pool_ids = [p.id for p in db.query(ETFPools).all()]

        for pool_id in pool_ids:
            try:
                with SessionLocal() as db:
                    service = ReportService(db)
                    metadata = service.generate_pool_report(
                        pool_id=pool_id,
                        report_type="pool_weekly",
                        format="html",
                    )
                print(
                    f"[Scheduler] Weekly report for pool {pool_id}: {metadata.status}"
                )
            except Exception as e:
                print(f"[Scheduler] Failed to generate report for pool {pool_id}: {e}")


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
        with SessionLocal() as db:
            pipeline = USEtfDiscoveryPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] US ETF discovery: success={result.success}, "
                f"records={result.records}"
            )


def run_us_stock_discovery():
    """Run the US stock discovery pipeline (weekly Sunday 02:00).

    Fetches S&P 500 constituents from FMP and upserts them as
    instrument_type="STOCK", market="US" into etf_info.
    """
    with redis_lock("us_stock_discovery", expire_seconds=7200) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] US stock discovery skipped: lock in use")
            return
        with SessionLocal() as db:
            pipeline = USStockDiscoveryPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] US stock discovery: success={result.success}, "
                f"records={result.records}"
            )


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
        with SessionLocal() as db:
            pipeline = USStockEnrichmentPipeline(db, batch_size=200)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] US stock enrichment: success={result.success}, "
                f"records={result.records}"
            )


def run_etf_scan():
    """Run the ETF market scan (Sunday 03:00)."""
    with redis_lock("etf_scan", expire_seconds=7200) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] ETF scan skipped: lock in use")
            return
        with SessionLocal() as db:
            service = ETFScannerService(db)
            result = service.scan_market()
            total = len(result.get("new", [])) + len(result.get("delisted", [])) + len(result.get("changed", []))
            print(f"[Scheduler] ETF scan: {total} changes found")


def run_etf_metadata_enrichment():
    """Run the ETF metadata enrichment pipeline (Sunday 04:00).

    Fills missing ETF product metadata (manager, category, underlying index,
    fund size, inception_date, list_date) from Tushare fund_basic.
    """
    with redis_lock("etf_metadata_enrichment", expire_seconds=7200) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] ETF metadata enrichment skipped: lock in use")
            return
        with SessionLocal() as db:
            pipeline = ETFMetadataEnrichmentPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] ETF metadata enrichment: "
                f"success={result.success}, records={result.records}"
            )


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
        with SessionLocal() as db:
            pipeline = ETFHoldingsPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] ETF holdings: "
                f"success={result.success}, records={result.records}"
            )


def run_listing_events():
    """Refresh the listing_events table from Tushare (daily 09:30).

    Free-tier users are gracefully handled: the pipeline falls back to
    stock_basic + 30-day window when ``new_share`` is denied.
    """
    with redis_lock("listing_events_daily", expire_seconds=3600, wait_timeout=600) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Listing events refresh skipped: lock in use")
            return
        with SessionLocal() as db:
            pipeline = ListingEventsPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] Listing events refresh: "
                f"success={result.success}, records={result.records}"
            )


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

        with SessionLocal() as db:
            pipeline = CryptoDailyPipeline(db, target_date=target_date)
            result = pipeline.run_with_retry(max_attempts=3)
            print(
                f"[Scheduler] Crypto ETL (target={target_date}): "
                f"success={result.success}, records={result.records}"
            )


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

        calculate_indicators.delay(
            target_date=target_date.isoformat() if target_date else None,
            full_history=False,
            market_filter="CRYPTO",
        )
        print(f"[Scheduler] Crypto indicator calculation task submitted (target={target_date})")


def run_futures_contract_refresh():
    """Refresh the futures main contract list (monthly day-1 at 03:00)."""
    with redis_lock("futures_contracts_refresh", expire_seconds=3600) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Futures contract refresh skipped: lock in use")
            return
        with SessionLocal() as db:
            pipeline = FuturesContractDiscoveryPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] Futures contract refresh: success={result.success}, "
                f"records={result.records}"
            )


def run_futures_daily(target_date: date | None = None):
    """Run the futures daily bars ETL pipeline.

    Scheduled at 16:30 Asia/Shanghai — 30 minutes after Chinese commodity
    futures markets close.
    """
    with redis_lock("futures_daily", expire_seconds=3600) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Futures daily skipped: lock in use")
            return
        with SessionLocal() as db:
            pipeline = FuturesDailyPipeline(db, target_date=target_date)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] Futures daily (target={target_date}): "
                f"success={result.success}, records={result.records}"
            )


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
        with SessionLocal() as db:
            pipeline = SecEdgarPipeline(db, batch_size=50)
            result = pipeline.run_with_retry(max_attempts=1)
            print(
                f"[Scheduler] SEC EDGAR refresh: "
                f"success={result.success}, records={result.records}"
            )


def run_microstructure_daily():
    """Refresh A-share micro-structure tables (daily 18:30 Asia/Shanghai).

    Runs the 4 sub-tasks (LHB / HSGT / margin / restricted) each in
    its own try/except guard — one failure does not abort the others.
    """
    with redis_lock("microstructure_daily", expire_seconds=3600) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Microstructure refresh skipped: lock in use")
            return
        with SessionLocal() as db:
            pipeline = MicrostructurePipeline(db)
            result = pipeline.run_with_retry(max_attempts=1)
            print(
                f"[Scheduler] Microstructure refresh: "
                f"success={result.success}, records={result.records}"
            )


def run_fund_flow_daily():
    """Refresh A-share fund-flow tables (daily 17:30 Asia/Shanghai).

    4 个 sub-task (individual / sector / etf / signals) 各自独立 try/except，
    单源失败不阻塞其他数据源。  调度时间设在 A 股收盘 15:00 之后 2.5 小时，
    既能拿到当天的稳定数据，又在 18:30 microstructure 之前完成。
    """
    with redis_lock("fund_flow_daily", expire_seconds=3600) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Fund-flow refresh skipped: lock in use")
            return
        with SessionLocal() as db:
            pipeline = FundFlowPipeline(db)
            result = pipeline.run_with_retry(max_attempts=1)
            print(
                f"[Scheduler] Fund-flow refresh: "
                f"success={result.success}, records={result.records}, "
                f"warnings={len(result.warnings)}"
            )


def run_market_fund_flow_daily(target_date: date | None = None):
    """Refresh 大盘资金流表 (daily 18:35 Asia/Shanghai)。

    在 ``fund_flow_daily`` (17:30) 与 ``microstructure_daily`` (18:30)
    之后执行，确保 ``individual_fund_flow`` 已落地，可据此派生沪市/深市
    净流入。写入 ``market_fund_flow`` 的 ``ALL`` / ``SH`` / ``SZ`` 三行。
    """
    with redis_lock("market_fund_flow_daily", expire_seconds=3600) as acquired:
        if not acquired:
            print(
                "⚠️ [SCHEDULER_WARN] Market fund-flow refresh skipped: lock in use"
            )
            return
        with SessionLocal() as db:
            pipeline = MarketFundFlowPipeline(db, target_date=target_date)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] Market fund-flow refresh: "
                f"success={result.success}, records={result.records}, "
                f"warnings={len(result.warnings)}"
            )


def run_search_trends_daily():
    """Refresh Xueqiu-derived search-trend observations (daily 03:00 Asia/Shanghai).

    Pulls one observation per (rotated) keyword for each of the two
    slots — ``baidu`` → Xueqiu 关注排行榜, ``google`` → Xueqiu
    分享交易排行榜 — and upserts into the ``search_trends`` table.
    Xueqiu is fast (~1-2s per slot) so the daily refresh covers the
    full keyword registry in a single run.
    """
    with redis_lock("search_trends_daily", expire_seconds=1800) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Search trends refresh skipped: lock in use")
            return
        with SessionLocal() as db:
            pipeline = SearchTrendsPipeline(db)
            result = pipeline.run_with_retry(max_attempts=1)
            print(
                f"[Scheduler] Search trends refresh: "
                f"success={result.success}, records={result.records}"
            )


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
        with SessionLocal() as db:
            pipeline = ResearchReportsPipeline(db)
            result = pipeline.run_with_retry(max_attempts=2)
            print(
                f"[Scheduler] Research-reports daily: "
                f"success={result.success}, records={result.records}"
            )


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
        with SessionLocal() as db:
            service = ResearchReportService(db)
            count = service.summarize_pending_reports(batch_size=20, max_per_run=20)
            print(f"[Scheduler] Research-reports summarize: {count} summarized")


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
        with SessionLocal() as db:
            from app.services.paper_trading_service import PaperTradingService

            service = PaperTradingService(db)
            updated = service.update_market_values()
            print(f"[Scheduler] Paper trade market update: {updated} positions refreshed")


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
        # Fetch account IDs in a short session; each account trades in its own
        # session so a long-running trade does not hold a connection.
        with SessionLocal() as db:
            from app.services.paper_trading_service import PaperTradingService

            service = PaperTradingService(db)
            account_ids = [acct.id for acct in service.get_accounts()]

        total_orders = 0
        for account_id in account_ids:
            try:
                with SessionLocal() as db:
                    service = PaperTradingService(db)
                    orders = service.auto_trade_from_signals(account_id)
                    total_orders += len(orders)
            except Exception:
                continue
        print(
            f"[Scheduler] Paper trade auto: {total_orders} orders "
            f"across {len(account_ids)} accounts"
        )


def run_signal_generation(target_date: date | None = None):
    """Generate trading signals for all active strategies (daily 09:00).

    Args:
        target_date: If provided, generate signals for this date instead of today.
    """
    # Short-lived session: only read config and the instrument universe.
    with SessionLocal() as db:
        # Scheduler-generated signals are owned by the system admin (id=1).
        default_user_id = db.query(User.id).filter(User.id == 1).scalar() or 1

        # Query active strategy configs directly (bypass StrategyService which
        # requires user_id scoping — the scheduler operates system-wide).
        active_configs = (
            db.query(StrategyConfig)
            .filter(StrategyConfig.is_active.is_(True))
            .all()
        )
        active_strategies = [
            {
                "id": s.id,
                "strategy_type": s.strategy_type,
                "params": s.params,
            }
            for s in active_configs
        ]

        # Get all active instruments (ETFs, stocks, crypto).
        etfs = db.query(ETFInfo).filter(ETFInfo.status == "active").all()

    expire_seconds = max(1800, min(14400, len(active_strategies) * len(etfs) * 2))

    with redis_lock(_LOCK_DAILY_PIPELINE, expire_seconds=expire_seconds, wait_timeout=1800) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Signal generation skipped: could not acquire pipeline lock")
            return

        # Create a fresh session for the actual signal generation so the
        # config-reading session above can be closed promptly.
        with SessionLocal() as db:
            signal_service = SignalService(db)
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
                            user_id=default_user_id,
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
                                    user_id=default_user_id,
                                )
                                total_signals += len(signals)
                            except Exception as e:
                                print(f"[Scheduler] Signal generation failed for {etf.code}: {e}")
                except Exception as e:
                    print(f"[Scheduler] Signal generation failed for strategy {strategy_id}: {e}")

            print(f"[Scheduler] Signal generation (target={target_date}): {total_signals} signals generated")


def run_cninfo_reports_daily():
    """Refresh cninfo periodic reports (daily 17:00 Asia/Shanghai).

    Offloads the actual work to a dedicated Celery worker so a backend
    container restart does not interrupt the nightly B-tier (HS300 + CS500)
    report fetch. The task is idempotent thanks to the unique constraint on
    ``announcement_id``.
    """
    with redis_lock("cninfo_reports_daily", expire_seconds=7200, wait_timeout=600) as acquired:
        if not acquired:
            print("⚠️ [SCHEDULER_WARN] Cninfo reports refresh skipped: lock in use")
            return
        result = refresh_cninfo_reports_daily.delay()
        print(f"[Scheduler] Cninfo reports daily queued: task_id={result.id}")


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
      - A-share adj_factor full-history backfill weekly Sunday 03:30
      - Indicator calculation at 08:00 daily (A-share market only)
      - A-share indicator fallback at 17:00 daily (covers ETF + STOCK
        even when one of the two daily-bar ETLs was delayed)
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
    # Clean up any ETL jobs that were killed during a previous deployment
    # before starting today's schedule.
    try:
        cleaned = cleanup_stuck_etl_jobs()
        if cleaned:
            print(f"[Scheduler] Cleaned up {cleaned} stuck ETL job(s) on startup")
    except Exception:
        logging.getLogger(__name__).exception(
            "Startup stuck-ETL cleanup failed; continuing anyway"
        )
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
    # 2026-07-19：磁盘监控（/data + /），每整点检查一次。
    # 阈值：80% warn / 95% error（基于 /data resize2fs 后 118GB）。
    # 没有 Prometheus / Grafana，靠 docker logs backend 检索；下次接监控时
    # 把 check_disk_usage() 的返回值直接吐到 metric 文件即可。
    scheduler.add_job(
        check_disk_usage,
        trigger=CronTrigger(hour="*", minute=15, timezone="Asia/Shanghai"),
        id="disk_usage_check",
        name="/data 与 / 磁盘使用率检查",
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
    # ── A-Share Indicator Fallback (17:00 Asia/Shanghai) ──
    # Defensive second pass: by 17:00 the ETF ETL (15:30) and STOCK
    # ETL (16:00) have both finished (with their internal
    # ``run_with_retry`` exhausted), so re-running the indicator calc
    # here guarantees the etf_indicator table for the current trade
    # date contains both ETF + STOCK rows even if the 08:00 run fired
    # before one of the two ETLs landed. Idempotent UPSERT, so a
    # no-op re-run is cheap.
    scheduler.add_job(
        run_a_share_indicator_fallback,
        trigger=CronTrigger(hour=17, minute=0, timezone="Asia/Shanghai"),
        id="a_share_indicator_fallback",
        name="A股指标17点兜底补算",
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
    # ── A-Share adj_factor full-history backfill ──
    # Weekly catch-up for dividend/split adjustments. The daily stock ETL
    # only writes the target date; this job refreshes the entire history so
    # older ex-dividend events are correctly reflected.
    scheduler.add_job(
        run_a_share_adj_factor_backfill,
        trigger=CronTrigger(
            day_of_week="sun", hour=3, minute=30, timezone="Asia/Shanghai"
        ),
        id="a_share_adj_factor_backfill",
        name="A股复权因子全历史回填",
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
        from app.core.redis_client import get_redis_client, redis_lock

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
            run_caixin_crawl, run_chinanews_finance_crawl,
            run_cninfo_crawl, run_huxiu_crawl, run_jiemian_crawl,
            run_kr36_crawl,
            run_sina_crawl, run_stats_gov_crawl, run_wallstreetcn_crawl,
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
        # New Chinese news sources (added 2026-07-18)
        scheduler.add_job(
            run_wallstreetcn_crawl,
            trigger=IntervalTrigger(minutes=5),
            id="news_wallstreetcn_5m",
            name="华尔街见闻 7x24",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_kr36_crawl,
            trigger=IntervalTrigger(minutes=10),
            id="news_36kr_10m",
            name="36氪快讯",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_huxiu_crawl,
            trigger=IntervalTrigger(minutes=10),
            id="news_huxiu_10m",
            name="虎嗅 RSS",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_jiemian_crawl,
            trigger=IntervalTrigger(minutes=10),
            id="news_jiemian_10m",
            name="界面新闻 RSS",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_caixin_crawl,
            trigger=IntervalTrigger(minutes=10),
            id="news_caixin_10m",
            name="财新最新文章",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_chinanews_finance_crawl,
            trigger=IntervalTrigger(minutes=15),
            id="news_chinanews_finance_15m",
            name="中新网财经",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_stats_gov_crawl,
            trigger=IntervalTrigger(minutes=30),
            id="news_stats_gov_30m",
            name="国家统计局数据发布",
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
    # ── Fund Flow (方案 C) ── daily 17:30 Asia/Shanghai
    # A 股盘后 2.5h (留 1h 给 microstructure 18:30 之前完成)
    scheduler.add_job(
        run_fund_flow_daily,
        trigger=CronTrigger(hour=17, minute=30, timezone="Asia/Shanghai"),
        id="fund_flow_daily",
        name="A 股免费资金流日刷",
        replace_existing=True,
        max_instances=1,
    )
    # ── Market Fund Flow (Phase 2.10) ── daily 18:35 Asia/Shanghai
    # 在 fund_flow_daily 与 microstructure_daily 之后，利用已落地的
    # individual_fund_flow 派生 SH/SZ 大盘净流入。
    scheduler.add_job(
        run_market_fund_flow_daily,
        trigger=CronTrigger(hour=18, minute=35, timezone="Asia/Shanghai"),
        id="market_fund_flow_daily",
        name="A 股大盘资金流日刷",
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
    # ── Stuck ETL cleanup ── hourly, so a killed job never blocks the
    # next scheduled run for more than an hour.
    scheduler.add_job(
        cleanup_stuck_etl_jobs,
        trigger=CronTrigger(hour="*", minute=45),
        id="cleanup_stuck_etl_jobs",
        name="清理卡死的ETL任务",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_sw_industry_index_refresh,
        trigger=CronTrigger(
            day_of_week="mon", hour=9, minute=30, timezone="Asia/Shanghai"
        ),
        id="sw_industry_index_refresh",
        name="申万一级行业指数回报刷新 (Phase 3)",
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
