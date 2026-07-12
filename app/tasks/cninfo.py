"""Celery tasks for cninfo report backfill.

These tasks offload network-I/O-heavy periodic report fetching from the
backend container to dedicated celery workers.
"""

import json
import logging
import time
from datetime import date, timedelta
from pathlib import Path

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.data.providers.cninfo_provider import CninfoProvider
from app.services.cninfo_report_service import CninfoReportService

log = logging.getLogger("celery.cninfo")

_ORG_IDS_PATH = Path(__file__).resolve().parent.parent / "data" / "static" / "cninfo_org_ids.json"
_ALL_TYPES = ("annual", "semi", "q1", "q3")
_ETA_INTERVAL = 50


def _load_ts_codes() -> list[str]:
    """Read cninfo org-id mapping and return sorted ts_codes."""
    if not _ORG_IDS_PATH.exists():
        raise RuntimeError(f"org_id mapping not found at {_ORG_IDS_PATH}")
    data = json.loads(_ORG_IDS_PATH.read_text(encoding="utf-8"))
    return sorted(k for k in data if not k.startswith("_"))


@celery_app.task(bind=True, max_retries=2, default_retry_delay=60)
def backfill_cninfo_reports(
    self,
    offset: int,
    limit: int,
    years: int = 5,
    report_type: str = "all",
) -> dict:
    """Backfill cninfo periodic reports for a shard of A-share stocks.

    Args:
        offset: Start index in the sorted ts_code list.
        limit: Number of stocks to process.
        years: How many years back from today to fetch.
        report_type: One of ``annual``, ``semi``, ``q1``, ``q3``, ``all``.

    Returns:
        Dict with ``processed``, ``written``, ``skipped`` counters.
    """
    all_codes = _load_ts_codes()
    shard = all_codes[offset : offset + limit]
    if not shard:
        return {"processed": 0, "written": 0, "skipped": 0}

    end_date = date.today()
    start_date = end_date - timedelta(days=years * 365)

    db = SessionLocal()
    service = CninfoReportService(db)
    total_written = 0
    total_skipped = 0
    t0 = time.time()

    for idx, ts_code in enumerate(shard):
        iter_start = time.time()
        try:
            if report_type == "all":
                written = service.fetch_for_stock(ts_code, start_date, end_date)
            else:
                provider = service.provider
                org_id = provider.get_org_id(ts_code)
                if not org_id:
                    total_skipped += 1
                    continue
                raw = provider.fetch_announcements(
                    org_id=org_id,
                    start_date=start_date,
                    end_date=end_date,
                    period_type=report_type,
                )
                written = 0
                stock_code = ts_code.split(".")[0]
                for rec in raw:
                    try:
                        written += service._upsert(rec, ts_code, stock_code, org_id)
                    except Exception:
                        pass
            if written > 0:
                total_written += written
        except Exception as exc:
            log.warning("[%d/%d] %s FAILED: %s", idx + 1, len(shard), ts_code, exc)
            continue

        elapsed = time.time() - iter_start
        if (idx + 1) % _ETA_INTERVAL == 0:
            done = idx + 1
            avg = (time.time() - t0) / done
            eta_min = (len(shard) - done) * avg / 60
            log.info(
                "[%d/%d] progress — written=%d skipped=%d avg=%.1fs/stock eta=%.0fmin",
                done,
                len(shard),
                total_written,
                total_skipped,
                avg,
                eta_min,
            )

    db.close()

    total_time = time.time() - t0
    log.info(
        "DONE shard [%d:%d] — %d stocks, written %d rows, skipped %d, %.0fs",
        offset,
        offset + limit,
        len(shard),
        total_written,
        total_skipped,
        total_time,
    )
    return {
        "processed": len(shard),
        "written": total_written,
        "skipped": total_skipped,
    }
