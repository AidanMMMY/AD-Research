"""Scheduler introspection & ad-hoc trigger service (ops P1-1 / P1-4).

Consumes — never mutates — the scheduler registration in
``app.core.scheduler``. Responsibilities:

* :func:`list_jobs`   — merge the cross-worker job snapshot (id, name,
  next_run) with the most recent ``etl_log`` row for each job so the ops
  dashboard can show ``last_run`` / ``last_status`` / ``last_duration_ms``
  / ``last_error``.
* :func:`run_now`     — fire a registered job once, out of band.
* :func:`trigger_etl_rerun` — the same, wrapped with a completion / failure
  notification through :class:`NotificationService`.

Why we run the job function directly in a daemon thread rather than nudging
APScheduler's ``next_run_time``: the scheduler ``BackgroundScheduler`` only
runs in the *leader* worker (``ENABLE_SCHEDULER`` + flock, see
``app.main``), so the worker handling this HTTP request usually has no live
job object to modify. Every ``run_*`` function in ``app.core.scheduler``
already guards itself with a ``redis_lock``, so an ad-hoc invocation is
safe: if the scheduled instance is mid-run, the manual run no-ops on the
lock instead of double-processing.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.log_sanitize import sanitize
from app.models.etl import ETLLog

logger = logging.getLogger(__name__)


class JobNotRunnable(Exception):
    """Raised when a job id has no callable registered for ad-hoc runs."""


def _job_registry() -> dict[str, Callable[..., Any]]:
    """Map scheduler job id → the zero-arg callable that executes it.

    Imported lazily to avoid paying ``app.core.scheduler``'s heavy pipeline
    imports at module-load time and to sidestep import cycles.
    """
    from app.core import scheduler as sc

    return {
        # ── US ──
        "us_daily_etl": sc.run_us_etl,
        "us_historical_backfill": sc.run_us_historical_backfill,
        "us_indicator_calculation": sc.run_us_indicator_calculation,
        "us_etf_discovery": sc.run_us_etf_discovery,
        "us_stock_discovery": sc.run_us_stock_discovery,
        "us_stock_enrichment": sc.run_us_stock_enrichment,
        # ── A-share ──
        "a_share_daily_etl": sc.run_a_share_etl,
        "a_stock_daily_etl": sc.run_a_share_stock_etl,
        "a_stock_fundamental_etl": sc.run_a_share_stock_fundamental,
        "a_stock_discovery": sc.run_a_share_stock_discovery,
        "a_stock_financials": sc.run_a_share_stock_financials,
        "indicator_calculation": sc.run_indicator_calculation,
        "a_share_indicator_fallback": sc.run_a_share_indicator_fallback,
        "score_calculation": sc.run_score_calculation,
        "signal_generation": sc.run_signal_generation,
        "etf_market_scan": sc.run_etf_scan,
        "etf_metadata_enrichment": sc.run_etf_metadata_enrichment,
        "etf_holdings": sc.run_etf_holdings,
        "listing_events_daily": sc.run_listing_events,
        "cninfo_reports_daily": sc.run_cninfo_reports_daily,
        "microstructure_daily": sc.run_microstructure_daily,
        "fund_flow_daily": sc.run_fund_flow_daily,
        "search_trends_daily": sc.run_search_trends_daily,
        "china_macro_daily": sc.run_china_macro_refresh,
        "global_indices_daily": sc.run_global_indices_refresh,
        "weekly_pool_reports": sc.run_weekly_pool_reports,
        "research_reports_daily": sc.run_research_reports_daily,
        "research_summarize": sc.run_summarize_pending_reports,
        # ── Crypto ──
        "crypto_daily_etl": sc.run_crypto_etl,
        "crypto_indicator_calculation": sc.run_crypto_indicator_calculation,
        # ── Futures ──
        "futures_daily_etl": sc.run_futures_daily,
        "futures_contracts_refresh": sc.run_futures_contract_refresh,
        # ── Paper trading ──
        "paper_trade_market_update": sc.run_paper_trade_market_update,
        "paper_trade_auto": sc.run_paper_trade_auto,
        # ── SEC ──
        "sec_edgar_daily": sc.run_sec_edgar_daily,
    }


def _latest_log(db: Session, job_name: str) -> ETLLog | None:
    return (
        db.query(ETLLog)
        .filter(ETLLog.job_name == job_name)
        .order_by(desc(ETLLog.created_at))
        .first()
    )


def _duration_ms(log: ETLLog) -> int | None:
    if not log.start_time or not log.end_time:
        return None
    start, end = log.start_time, log.end_time
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    delta = (end - start).total_seconds()
    return int(round(delta * 1000)) if delta >= 0 else None


def list_jobs(db: Session) -> list[dict[str, Any]]:
    """Return every registered scheduler job with its last-run stats.

    Each item::

        {
          "id", "name", "next_run",
          "last_run", "last_status", "last_duration_ms", "last_error",
          "runnable": bool,   # has a callable for run-now
        }
    """
    from app.core.scheduler import get_scheduler_jobs

    registry = _job_registry()
    jobs = get_scheduler_jobs()

    out: list[dict[str, Any]] = []
    for job in jobs:
        job_id = job.get("id")
        log = _latest_log(db, job_id) if job_id else None
        out.append(
            {
                "id": job_id,
                "name": job.get("name") or job_id,
                "next_run": job.get("next_run_time"),
                "last_run": (
                    log.created_at.isoformat() if log and log.created_at else None
                ),
                "last_status": (log.status if log else None),
                "last_duration_ms": (_duration_ms(log) if log else None),
                "last_error": (log.error_msg if log else None),
                "runnable": job_id in registry,
            }
        )
    return out


def _run_and_notify(job_id: str, func: Callable[..., Any], notify: bool) -> None:
    """Execute ``func`` synchronously (called inside a daemon thread).

    On completion, optionally dispatch a NotificationService alert so the
    ops team learns the ad-hoc run's outcome.
    """
    error: str | None = None
    try:
        func()
    except Exception as exc:  # noqa: BLE001 — capture, report, never re-raise
        error = str(exc)
        logger.error(
            "Ad-hoc run of job %s failed: %s", job_id, sanitize(error)
        )
    else:
        logger.info("Ad-hoc run of job %s completed", job_id)

    if not notify:
        return

    # Fire the completion / failure alert on its own session — the run may
    # have taken minutes and the request session is long gone.
    from app.core.database import SessionLocal
    from app.services.notification_service import NotificationService

    db = SessionLocal()
    try:
        service = NotificationService(db)
        if error:
            service.send_etl_alert(job_id, error)
        else:
            service.send_etl_completion(
                job_id, status="success", detail="手动重跑完成"
            )
    except Exception:  # pragma: no cover — alerting must not crash the thread
        logger.exception("Failed to dispatch ad-hoc run notification for %s", job_id)
    finally:
        db.close()


def run_now(job_id: str, *, notify: bool = False) -> dict[str, Any]:
    """Fire a registered scheduler job once, out of band.

    Returns ``{"task_id", "job_name", "queued_at"}``. Raises
    :class:`JobNotRunnable` if the job id is unknown.
    """
    registry = _job_registry()
    func = registry.get(job_id)
    if func is None:
        raise JobNotRunnable(job_id)

    task_id = uuid.uuid4().hex
    queued_at = datetime.now(timezone.utc).isoformat()

    thread = threading.Thread(
        target=_run_and_notify,
        args=(job_id, func, notify),
        name=f"run-now-{job_id}-{task_id[:8]}",
        daemon=True,
    )
    thread.start()

    logger.info("Queued ad-hoc run task=%s job=%s notify=%s", task_id, job_id, notify)
    return {"task_id": task_id, "job_name": job_id, "queued_at": queued_at}


def trigger_etl_rerun(job_name: str, force: bool = False) -> dict[str, Any]:
    """One-shot ETL re-run wired to a completion notification (ops P1-4).

    ``force`` is accepted for API symmetry; because every ``run_*`` function
    already serialises on a redis_lock, a re-run is naturally idempotent and
    ``force`` currently only documents caller intent (it does not bypass the
    lock — doing so could corrupt an in-flight write).
    """
    result = run_now(job_name, notify=True)
    result["force"] = bool(force)
    return result
