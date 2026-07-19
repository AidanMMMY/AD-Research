#!/usr/bin/env python3
"""Clean up ETL jobs that are stuck in the ``running`` state.

When an ETL process is SIGKILLed or a container is restarted, the
``ETLLog`` row stays at ``status='running'`` and the Redis lock may still
be held.  This script marks those rows as ``failed`` and removes the
associated Redis locks so the next scheduler run can proceed.

Usage (inside container):
    cd /app && PYTHONPATH=/app python3 scripts/cleanup_stuck_etl_logs.py

Exit codes:
    0 - nothing stuck or cleanup succeeded
    1 - cleanup encountered errors
"""

import logging
import sys
from datetime import datetime, timedelta, timezone

from app.core.database import SessionLocal
from app.core.redis_client import get_redis_client
from app.models.etl import ETLLog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cleanup_stuck_etl_logs")

# Maps ETLLog.job_name -> Redis lock name used by the scheduler.
# Keep this in sync with app/core/scheduler.py.
_JOB_LOCK_MAP: dict[str, str | list[str]] = {
    "a_share_daily_etl": "daily_pipeline",
    "a_stock_daily_etl": "a_stock_daily_pipeline",
    "a_share_fundamental_etl": "a_stock_fundamental_pipeline",
    "a_share_discovery_etl": "a_stock_discovery",
    "a_share_financials_etl": "a_stock_financials",
    "us_daily_etl": "us_daily_pipeline",
    "us_historical_backfill": "us_backfill_pipeline",
    "us_etf_discovery": "us_etf_discovery",
    "us_stock_discovery": "us_stock_discovery",
    "us_stock_enrichment": "us_stock_enrichment",
    "crypto_daily_etl": "crypto_daily_pipeline",
    "weekly_pool_reports": "weekly_pool_reports",
    "etf_scan": "etf_scan",
    "etf_metadata_enrichment": "etf_metadata_enrichment",
    "etf_holdings": "etf_holdings",
    "listing_events_daily": "listing_events_daily",
    "futures_contracts_refresh": "futures_contracts_refresh",
    "futures_daily": "futures_daily",
    "sec_edgar_daily": "sec_edgar_daily",
    "microstructure_daily": "microstructure_daily",
    "fund_flow_daily": "fund_flow_daily",
    "research_reports_daily": "research_reports_daily",
    "search_trends_daily": "search_trends_daily",
    "china_macro_daily": "china_macro_daily",
    "global_indices_daily": "global_indices_daily",
    "cninfo_reports_daily": "cninfo_reports_daily",
}

# Any running job older than this is considered stuck.
DEFAULT_STUCK_THRESHOLD_MINUTES = 120


def _lock_names_for_job(job_name: str) -> list[str]:
    """Return Redis lock name(s) that may belong to a given ETL job."""
    mapped = _JOB_LOCK_MAP.get(job_name)
    names: list[str] = []
    if mapped:
        if isinstance(mapped, list):
            names.extend(mapped)
        else:
            names.append(mapped)
    # Fallback: some jobs use the job_name itself as the lock key.
    if job_name not in names:
        names.append(job_name)
    return names


def main() -> int:
    threshold_minutes = int(
        sys.argv[1] if len(sys.argv) > 1 else DEFAULT_STUCK_THRESHOLD_MINUTES
    )
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)

    db = SessionLocal()
    redis_client = get_redis_client()
    errors: list[str] = []

    try:
        stuck_logs = (
            db.query(ETLLog)
            .filter(ETLLog.status == "running")
            .filter(ETLLog.start_time < cutoff)
            .order_by(ETLLog.start_time.asc())
            .all()
        )

        if not stuck_logs:
            logger.info("No stuck ETL jobs found (threshold=%d min)", threshold_minutes)
            return 0

        logger.warning(
            "Found %d stuck ETL job(s) older than %d minutes",
            len(stuck_logs),
            threshold_minutes,
        )

        for log in stuck_logs:
            job_name = log.job_name or "unknown"
            start = log.start_time.isoformat() if log.start_time else "?"
            logger.info("Cleaning up %s (started %s)", job_name, start)

            log.status = "failed"
            log.end_time = datetime.now(timezone.utc)
            log.error_msg = (
                log.error_msg or ""
            ) + "; [cleanup] process terminated or lease expired"

            for lock_name in _lock_names_for_job(job_name):
                lock_key = f"lock:{lock_name}"
                try:
                    deleted = redis_client.delete(lock_key)
                    if deleted:
                        logger.info("  Released Redis lock %s", lock_key)
                except Exception as exc:
                    msg = f"Failed to delete Redis lock {lock_key}: {exc}"
                    logger.error("  %s", msg)
                    errors.append(msg)

        try:
            db.commit()
            logger.info("Updated %d ETL log row(s) to failed", len(stuck_logs))
        except Exception as exc:
            db.rollback()
            logger.exception("Failed to commit ETL log cleanup")
            return 1

        if errors:
            logger.warning("Cleanup completed with %d Redis error(s)", len(errors))
            return 1

        return 0

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
