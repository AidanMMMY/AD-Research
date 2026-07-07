#!/usr/bin/env python3
"""Chunked A-share indicator recalculation with checkpointing.

Re-calculates technical (MA/RSI/MACD/Bollinger/ATR) and risk/return
indicators for all active A-share instruments. Processes instruments in
configurable batches, commits per batch, tracks progress on disk, and can
resume after interruption or OOM.

Usage inside backend container:
    # test run on first 100 instruments
    cd /app && PYTHONPATH=/app python3 scripts/chunked_recalc_a_share_indicators.py --limit 100 --batch-size 100

    # full run, resumable
    cd /app && PYTHONPATH=/app python3 scripts/chunked_recalc_a_share_indicators.py --batch-size 100

    # resume after failure with smaller batch
    cd /app && PYTHONPATH=/app python3 scripts/chunked_recalc_a_share_indicators.py --batch-size 50 --resume

Environment:
    DATABASE_URL is read from app config (same as the API).
"""

from __future__ import annotations

import argparse
import gc
import json
import logging
import os
import sys
import time
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

# Make app imports work when script is run from repo root inside container.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

from app.core.cache import cache_invalidate_pattern
from app.core.database import SessionLocal
from app.data.indicators.calculator import (
    _INDICATOR_COLUMNS,
    _build_indicator_record,
    _MIN_BARS,
    calculate_single_etf,
)
from app.models.etf import ETFInfo, ETFIndicator, InstrumentDailyBar
from app.models.etl import ETLLog

logger = logging.getLogger("chunked_recalc_a_share_indicators")

A_SHARE_MARKET = "A股"
DEFAULT_BATCH_SIZE = 100
DEFAULT_PROGRESS_FILE = "/tmp/chunked_recalc_a_share_progress.json"


def _get_process_memory_mb() -> float:
    """Return current process RSS memory in MB, if psutil is available."""
    if psutil is None:
        return 0.0
    try:
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except Exception:
        return 0.0


def _log_etl(
    db: Session,
    job_name: str,
    status: str,
    records_count: int,
    start_time: datetime,
    error_msg: str | None,
) -> None:
    """Write an ETLLog entry and commit."""
    log = ETLLog(
        job_name=job_name,
        status=status,
        start_time=start_time,
        end_time=datetime.now(),
        records_count=records_count,
        error_msg=error_msg,
    )
    db.add(log)
    db.commit()


def _load_progress(path: str) -> dict[str, Any]:
    """Load progress JSON; return empty dict if missing or corrupt."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_progress(path: str, progress: dict[str, Any]) -> None:
    """Atomically write progress JSON."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2, default=str)
    os.replace(tmp, path)


def _get_active_a_share_codes(
    db: Session,
    limit: int | None = None,
    offset: int = 0,
) -> list[tuple[str, date | None, date | None, date | None]]:
    """Return active A-share instrument codes with list/inception/delist dates."""
    stmt = (
        select(
            ETFInfo.code,
            ETFInfo.list_date,
            ETFInfo.inception_date,
            ETFInfo.delist_date,
        )
        .where(ETFInfo.status == "active")
        .where(ETFInfo.market == A_SHARE_MARKET)
        .order_by(ETFInfo.code.asc())
        .offset(offset)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return db.execute(stmt).all()


def _fetch_bars_for_code(
    db: Session,
    etf_code: str,
    list_date: date | None,
    target_date: date | None,
) -> pd.DataFrame:
    """Fetch daily bars for a single instrument and return as DataFrame."""
    stmt = (
        select(InstrumentDailyBar)
        .where(InstrumentDailyBar.etf_code == etf_code)
        .order_by(InstrumentDailyBar.trade_date.asc())
    )
    if list_date is not None:
        stmt = stmt.where(InstrumentDailyBar.trade_date >= list_date)
    if target_date is not None:
        stmt = stmt.where(InstrumentDailyBar.trade_date <= target_date)

    bars = db.execute(stmt).scalars().all()
    if not bars or len(bars) < _MIN_BARS:
        return pd.DataFrame()

    return pd.DataFrame(
        [
            {
                "trade_date": b.trade_date,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": float(b.close),
                "adj_close": float(b.close) * float(b.adj_factor or 1.0),
                "volume": b.volume,
                "amount": b.amount,
            }
            for b in bars
        ]
    )


def _upsert_indicator_records(
    db: Session,
    records: list[dict[str, Any]],
) -> int:
    """Bulk upsert indicator records. Returns number of records written."""
    if not records:
        return 0
    insert_stmt = insert(ETFIndicator).values(records)
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=["etf_code", "trade_date"],
        set_={col: insert_stmt.excluded[col] for col in _INDICATOR_COLUMNS},
    )
    db.execute(upsert_stmt)
    db.commit()
    return len(records)


def _process_single_instrument(
    db: Session,
    etf_code: str,
    list_date: date | None,
    inception_date: date | None,
    delist_date: date | None,
    target_date: date | None,
    full_history: bool,
) -> tuple[int, str | None]:
    """Calculate and upsert indicators for one instrument.

    Returns (records_updated, error_message).
    """
    effective_list_date = list_date or inception_date

    if target_date is not None and effective_list_date is not None and target_date < effective_list_date:
        return 0, None
    if target_date is not None and delist_date is not None and target_date > delist_date:
        return 0, None

    df = _fetch_bars_for_code(db, etf_code, effective_list_date, target_date)
    if df.empty:
        return 0, None

    try:
        result_df = calculate_single_etf(etf_code, df)
        if result_df.empty:
            return 0, None

        if full_history:
            records = [
                _build_indicator_record(etf_code, row)
                for _, row in result_df.iterrows()
            ]
        else:
            latest_row = result_df.iloc[-1]
            records = [_build_indicator_record(etf_code, latest_row)]

        if not records:
            return 0, None

        return _upsert_indicator_records(db, records), None
    except Exception as exc:
        db.rollback()
        return 0, f"{exc}\n{traceback.format_exc()}"
    finally:
        # Help free memory before next instrument.
        del df


def chunked_recalculate(
    db: Session,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    full_history: bool = True,
    target_date: date | None = None,
    limit: int | None = None,
    resume: bool = False,
    progress_file: str = DEFAULT_PROGRESS_FILE,
) -> dict[str, Any]:
    """Chunked recalculation entry point.

    Returns summary dict with counts, failures, timing.
    """
    start_time = datetime.now()
    progress = _load_progress(progress_file) if resume else {}

    # If resuming, respect the saved batch size unless overridden by caller.
    if resume and "batch_size" in progress and batch_size == DEFAULT_BATCH_SIZE:
        saved_batch = progress.get("batch_size")
        if isinstance(saved_batch, int) and saved_batch > 0:
            batch_size = saved_batch
            logger.info("Resuming with saved batch_size=%d", batch_size)

    total_processed = progress.get("total_processed", 0)
    total_records = progress.get("total_records", 0)
    failed_codes = list(progress.get("failed_codes", []))
    completed_codes = set(progress.get("completed_codes", []))

    # Discover total active A-share instruments.
    all_codes_rows = _get_active_a_share_codes(db)
    if limit is not None:
        all_codes_rows = all_codes_rows[:limit]
    all_codes = [row.code for row in all_codes_rows]
    total_codes = len(all_codes)
    logger.info("Found %d active A-share instruments to process", total_codes)

    # Filter out already-completed codes when resuming.
    pending_rows = [row for row in all_codes_rows if row.code not in completed_codes]
    logger.info("Pending instruments: %d", len(pending_rows))

    if not pending_rows:
        logger.info("No pending instruments; nothing to do.")
        return {
            "total_codes": total_codes,
            "total_processed": total_processed,
            "total_records": total_records,
            "failed_count": len(failed_codes),
            "failed_codes": failed_codes,
            "duration_seconds": 0,
        }

    # Process in batches.
    batch_start_idx = 0
    batch_number = 0
    while batch_start_idx < len(pending_rows):
        batch_number += 1
        batch_rows = pending_rows[batch_start_idx : batch_start_idx + batch_size]
        batch_codes = [row.code for row in batch_rows]
        batch_start_time = time.time()
        mem_before = _get_process_memory_mb()

        logger.info(
            "Batch %d | codes %d-%d | memory %.1f MB | starting",
            batch_number,
            total_processed + 1,
            total_processed + len(batch_rows),
            mem_before,
        )

        batch_records = 0
        batch_failures: list[str] = []

        for row in batch_rows:
            try:
                records, error = _process_single_instrument(
                    db,
                    row.code,
                    row.list_date,
                    row.inception_date,
                    row.delist_date,
                    target_date,
                    full_history,
                )
                if error:
                    failed_codes.append(row.code)
                    batch_failures.append(f"{row.code}: {error}")
                    logger.warning("Failed %s: %s", row.code, error[:200])
                else:
                    completed_codes.add(row.code)
                    total_processed += 1
                    total_records += records
                    batch_records += records
            except Exception:
                db.rollback()
                failed_codes.append(row.code)
                err = traceback.format_exc()
                batch_failures.append(f"{row.code}: {err}")
                logger.exception("Unexpected failure for %s", row.code)

        # Commit progress and force garbage collection after each batch.
        progress.update(
            {
                "batch_number": batch_number,
                "total_processed": total_processed,
                "total_records": total_records,
                "total_codes": total_codes,
                "batch_size": batch_size,
                "completed_codes": sorted(completed_codes),
                "failed_codes": failed_codes,
                "last_updated": datetime.now().isoformat(),
                "last_batch_codes": batch_codes,
                "last_batch_failures": batch_failures,
            }
        )
        _save_progress(progress_file, progress)

        # Expire all ORM instances to keep the identity map from growing
        # indefinitely across batches; this is the main leak path on long
        # full-history recalculation runs.
        try:
            db.expire_all()
        except Exception:
            logger.exception("expire_all failed after batch %d", batch_number)

        gc.collect()
        mem_after = _get_process_memory_mb()
        batch_duration = time.time() - batch_start_time

        logger.info(
            "Batch %d complete | records=%d | processed=%d/%d | "
            "duration=%.1fs | memory %.1f MB -> %.1f MB",
            batch_number,
            batch_records,
            total_processed,
            total_codes,
            batch_duration,
            mem_before,
            mem_after,
        )

        # Surface a clear warning if memory grew sharply; operator can lower
        # --batch-size or restart with --resume.
        mem_delta = mem_after - mem_before
        if mem_delta > 512:
            logger.warning(
                "Batch %d memory increased by %.1f MB (>512 MB). "
                "Consider reducing --batch-size and resuming.",
                batch_number,
                mem_delta,
            )

        batch_start_idx += batch_size

    duration = (datetime.now() - start_time).total_seconds()

    # Final cache invalidation.
    try:
        cache_invalidate_pattern("indicator:*")
        cache_invalidate_pattern("screen:*")
    except Exception:
        logger.exception("Failed to invalidate indicator/screen caches")

    # Final ETL log.
    status = "success" if not failed_codes else "partial"
    error_msg = (
        f"Failed {len(failed_codes)} instruments: {', '.join(failed_codes[:50])}"
        if failed_codes
        else None
    )
    _log_etl(db, "chunked_a_share_indicator_recalc", status, total_records, start_time, error_msg)

    summary = {
        "total_codes": total_codes,
        "total_processed": total_processed,
        "total_records": total_records,
        "failed_count": len(failed_codes),
        "failed_codes": failed_codes,
        "duration_seconds": duration,
        "batch_size": batch_size,
        "progress_file": progress_file,
    }
    logger.info("Chunked recalculation finished: %s", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Chunked A-share indicator recalculation",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Instruments per batch (default {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process first N instruments (useful for smoke test)",
    )
    parser.add_argument(
        "--target-date",
        type=str,
        default=None,
        help="Only recalculate up to YYYY-MM-DD (default: all history)",
    )
    parser.add_argument(
        "--full-history",
        action="store_true",
        default=True,
        help="Recalculate every historical trade date (default)",
    )
    parser.add_argument(
        "--latest-only",
        action="store_true",
        help="Recalculate only the latest trade date",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from progress file",
    )
    parser.add_argument(
        "--progress-file",
        type=str,
        default=DEFAULT_PROGRESS_FILE,
        help=f"Progress / checkpoint file (default {DEFAULT_PROGRESS_FILE})",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    target_date = None
    if args.target_date:
        target_date = datetime.strptime(args.target_date, "%Y-%m-%d").date()

    full_history = not args.latest_only

    db = SessionLocal()
    try:
        summary = chunked_recalculate(
            db,
            batch_size=args.batch_size,
            full_history=full_history,
            target_date=target_date,
            limit=args.limit,
            resume=args.resume,
            progress_file=args.progress_file,
        )
        print(json.dumps(summary, indent=2, default=str))
        return 0 if summary.get("failed_count", 0) == 0 else 2
    except Exception:
        logger.exception("Chunked recalculation aborted")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
