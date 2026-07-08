"""Quarterly ETF top-10 holdings refresh job.

A-share ETFs disclose their top-10 holdings on a quarterly cadence, with
the bulk of disclosures landing in three short windows:

- **4/20** — Q1 / annual report season (most fund companies publish
  their year-end + Q1 snapshots around this date).
- **8/30** — mid-year / semi-annual report deadline.
- **10/25** — Q3 report deadline.

This job runs ``ETFHoldingsPipeline`` once per window at 02:00
Asia/Shanghai (after the daily ETF bars are settled but before the
trading day starts) so the holdings are fresh by market open.  It is
independent of the daily 07:00 ``etf_holdings`` job — the daily job is
an opportunistic "try to refresh whatever is new" while this quarterly
job is the deterministic catch-up that fires whether the daily job
succeeded or not.

After every run we also evaluate the coverage SLO (see
``app.services.etf_holdings_coverage``) and log an alert when the
most recent snapshot is below the 7/14/30 day coverage thresholds.
The alert severity (WARN/ERROR) is driven by the threshold table.
This is the same path the dashboard hits via
``GET /api/v1/etf-holdings/coverage/latest`` so the alert log and
the UI stay in lockstep.

Manual trigger (force=True bypasses the in-flight lock):
    POST /api/v1/etf-holdings/refresh
    POST /api/v1/etf-holdings/refresh?force=true
"""

from __future__ import annotations

import logging
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.database import SessionLocal
from app.core.redis_client import redis_lock
from app.data.pipelines.etf_holdings import ETFHoldingsPipeline
from app.services.etf_holdings_coverage import (
    COVERAGE_THRESHOLDS,
    get_latest_coverage,
)

logger = logging.getLogger(__name__)

# Lock key — namespace under the shared "lock:" prefix used by
# ``app.core.redis_client.redis_lock``.  Two-hour TTL is generous enough
# for even the slowest of the three disclosure windows (Tushare's
# fund_portfolio can take ~90 minutes when an Akshare fallback is
# needed).
LOCK_KEY = "etf_holdings_quarterly"
LOCK_TTL_SECONDS = 7200

# Public (cron, no prefix) so other modules / dashboards can introspect.
QUARTERLY_TRIGGERS: list[tuple[str, int, int]] = [
    ("Q1 / annual reports", 4, 20),
    ("Mid-year reports", 8, 30),
    ("Q3 reports", 10, 25),
]


def _log_coverage_summary() -> dict[str, Any] | None:
    """Evaluate the coverage SLO and emit a single INFO + per-threshold alert.

    Each alert uses the severity configured in
    ``app.services.etf_holdings_coverage.COVERAGE_THRESHOLDS`` (WARN or
    ERROR).  Returns the coverage dict (or ``None`` when no snapshot
    exists yet) so callers / tests can introspect what was logged.
    """
    db = SessionLocal()
    try:
        coverage = get_latest_coverage(db)
        if coverage is None:
            logger.info(
                "[SCHEDULER] ETF holdings coverage: no snapshot landed yet"
            )
            return None

        summary = coverage.to_dict()
        logger.info(
            "[SCHEDULER] ETF holdings coverage: "
            "snapshot=%s etf_count=%s/%s (%.2f%%) days_ago=%d sources=%s",
            summary["snapshot_date"],
            summary["etf_count"],
            summary["eligible_etf_count"],
            summary["coverage_pct"],
            summary["days_ago"],
            summary["sources"],
        )

        for alert in coverage.coverage_alerts:
            threshold = alert["threshold_days"]
            min_pct = alert["min_coverage_pct"]
            actual = alert["actual_coverage_pct"]
            severity = alert.get("severity", "WARN")
            log_fn = logger.error if severity == "ERROR" else logger.warning
            log_fn(
                "[SCHEDULER] ETF holdings coverage SLO breach: "
                "%d-day threshold not met — actual=%.2f%% < expected=%.2f%% "
                "(snapshot=%s, days_ago=%d, severity=%s)",
                threshold,
                actual,
                min_pct,
                summary["snapshot_date"],
                summary["days_ago"],
                severity,
            )
        return summary
    except Exception as exc:  # noqa: BLE001 — coverage is best-effort
        logger.warning(
            "[SCHEDULER] ETF holdings coverage summary failed: %s", exc
        )
        return None
    finally:
        db.close()


def refresh_etf_holdings(force: bool = False) -> dict[str, Any]:
    """Run the batched ETF holdings ETL once.

    Args:
        force: If True, ignore the in-flight lock and run anyway.  Used
            by the manual-refresh API when the operator explicitly wants
            to re-run (e.g. after a deploy that aborted the last run).

    Returns:
        Dict with ``status`` (``ok`` / ``skipped`` / ``failed``) plus
        diagnostic fields.  Always returns a dict so callers (API and
        scheduler) can log / serialize uniformly.
    """
    if force:
        # Even when forcing, the lock context still tries to acquire —
        # we just ignore the acquisition result.  The lock is still
        # released in the finally block inside ``redis_lock``.
        logger.warning("[SCHEDULER] ETF holdings quarterly refresh forced (lock bypassed)")
        with redis_lock(LOCK_KEY, expire_seconds=LOCK_TTL_SECONDS) as acquired:
            return _run_pipeline(acquired=acquired, forced=True)

    with redis_lock(LOCK_KEY, expire_seconds=LOCK_TTL_SECONDS) as acquired:
        if not acquired:
            logger.info(
                "[SCHEDULER] ETF holdings quarterly refresh skipped: lock in use"
            )
            return {"status": "skipped", "reason": "already running"}
        return _run_pipeline(acquired=acquired, forced=False)


def _run_pipeline(acquired: bool, forced: bool) -> dict[str, Any]:
    """Execute the pipeline; shared body of forced and scheduled paths."""
    db = SessionLocal()
    try:
        pipeline = ETFHoldingsPipeline(db)
        result = pipeline.run_with_retry(max_attempts=2)
        payload: dict[str, Any] = {
            "status": "ok" if result.success else "failed",
            "records": result.records,
            "forced": forced,
            "lock_acquired": acquired,
        }
        if result.error:
            payload["error"] = result.error
        if result.warnings:
            payload["warnings"] = result.warnings

        # Coverage SLO evaluation — only run on successful ETL passes.
        if result.success:
            coverage = _log_coverage_summary()
            if coverage is not None:
                payload["coverage"] = coverage

        logger.info(
            "[SCHEDULER] ETF holdings quarterly refresh: "
            "status=%s records=%s forced=%s",
            payload["status"],
            result.records,
            forced,
        )
        return payload
    except Exception as exc:  # noqa: BLE001 — last-resort guard
        logger.exception("[SCHEDULER] ETF holdings quarterly refresh crashed")
        return {
            "status": "failed",
            "error": str(exc),
            "forced": forced,
            "lock_acquired": acquired,
        }
    finally:
        db.close()


def register(scheduler: BackgroundScheduler) -> None:
    """Register the three quarterly cron jobs on ``scheduler``.

    Each trigger fires at 02:00 Asia/Shanghai on its disclosure date.
    APScheduler IDs are namespaced ``etf_holdings_quarterly_<m>_<d>`` so
    the daily ``etf_holdings`` job (id ``etf_holdings``) does not
    collide and the quarterly set can be introspected / removed as a
    group.
    """
    for label, month, day in QUARTERLY_TRIGGERS:
        job_id = f"etf_holdings_quarterly_{month}_{day}"
        scheduler.add_job(
            refresh_etf_holdings,
            trigger=CronTrigger(
                month=month,
                day=day,
                hour=2,
                minute=0,
                timezone="Asia/Shanghai",
            ),
            id=job_id,
            name=f"ETF前十大持仓季度刷新 ({label})",
            replace_existing=True,
            max_instances=1,
            kwargs={"force": False},
        )
        logger.info(
            "[SCHEDULER] Registered quarterly ETF holdings refresh: "
            "%02d-%02d 02:00 Asia/Shanghai (id=%s, "
            "coverage_thresholds=%s)",
            month,
            day,
            job_id,
            [(d, p) for d, p, _ in COVERAGE_THRESHOLDS],
        )
