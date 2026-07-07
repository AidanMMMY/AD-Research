#!/usr/bin/env python3
"""Backfill adj_factor for A-share ETF daily bars.

Uses Tushare ``fund_adj`` interface to fetch the adjustment factor for every
(etf_code, trade_date) in ``instrument_daily_bar`` and updates the table.

The script is idempotent: re-running it will recompute and overwrite the same
rows. A JSON progress file keeps track of completed codes so the run can be
resumed after interruption.

Usage inside backend container:
    cd /app && PYTHONPATH=/app python3 scripts/backfill_etf_adj_factor.py

Dry run:
    cd /app && PYTHONPATH=/app python3 scripts/backfill_etf_adj_factor.py --dry-run

Resume after interruption:
    cd /app && PYTHONPATH=/app python3 scripts/backfill_etf_adj_factor.py --resume
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

# Make app imports work when script is run from repo root inside container.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

from app.core.database import SessionLocal
from app.data.providers.tushare_provider import TushareProvider
from app.models.etf import ETFInfo, InstrumentDailyBar

logger = logging.getLogger("backfill_etf_adj_factor")

DEFAULT_PROGRESS_FILE = "/tmp/backfill_etf_adj_factor_progress.json"
DEFAULT_BATCH_SIZE = 500
API_DELAY = 0.5  # Tushare rate limit buffer


def _to_internal_code(ts_code: str) -> str:
    """Convert Tushare ts_code to internal code (e.g. 510300.SH)."""
    return ts_code


def _load_progress(path: str) -> set[str]:
    """Load set of completed codes from progress file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("completed", []))
    except Exception:
        return set()


def _save_progress(path: str, completed: set[str], stats: dict[str, Any]) -> None:
    """Atomically write progress file."""
    tmp = path + ".tmp"
    payload = {
        "completed": sorted(completed),
        "stats": stats,
        "updated_at": datetime.utcnow().isoformat(),
    }
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    Path(tmp).replace(path)


def fetch_adjusted_factors(provider: TushareProvider, code: str) -> pd.DataFrame:
    """Fetch adjustment factors for a single ETF from Tushare fund_adj."""
    try:
        df = provider._pro.fund_adj(ts_code=code)
    except Exception as exc:
        logger.warning("Tushare fund_adj failed for %s: %s", code, exc)
        return pd.DataFrame(columns=["trade_date", "adj_factor"])

    if df is None or df.empty or "trade_date" not in df.columns or "adj_factor" not in df.columns:
        return pd.DataFrame(columns=["trade_date", "adj_factor"])

    df = df.rename(columns={"ts_code": "etf_code"})
    df["etf_code"] = df["etf_code"].apply(_to_internal_code)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df["adj_factor"] = pd.to_numeric(df["adj_factor"], errors="coerce")
    return df[["trade_date", "adj_factor"]].dropna(subset=["trade_date", "adj_factor"])


def backfill_code(db: Session, provider: TushareProvider, code: str, dry_run: bool = False) -> dict[str, Any]:
    """Backfill adj_factor for a single ETF code."""
    rows = (
        db.query(InstrumentDailyBar.trade_date, InstrumentDailyBar.close)
        .filter(InstrumentDailyBar.etf_code == code)
        .order_by(InstrumentDailyBar.trade_date)
        .all()
    )
    if not rows:
        return {"updated": 0, "skipped": 0, "reason": "no_daily_bars"}

    adj_df = fetch_adjusted_factors(provider, code)
    if adj_df.empty:
        return {"updated": 0, "skipped": len(rows), "reason": "no_adj_data"}

    trade_dates = [r.trade_date for r in rows]
    raw_df = pd.DataFrame({"trade_date": trade_dates})
    merged = raw_df.merge(adj_df, on="trade_date", how="left")

    updates = []
    for _, row in merged.iterrows():
        if pd.isna(row["adj_factor"]):
            continue
        updates.append(
            {
                "etf_code": code,
                "trade_date": row["trade_date"],
                "adj_factor": float(row["adj_factor"]),
            }
        )

    if dry_run:
        return {"updated": len(updates), "skipped": len(rows) - len(updates), "reason": "dry_run"}

    if updates:
        for u in updates:
            db.execute(
                text("""
                    UPDATE instrument_daily_bar
                    SET adj_factor = :adj_factor
                    WHERE etf_code = :etf_code
                      AND trade_date = :trade_date
                """),
                u,
            )
        db.commit()

    return {"updated": len(updates), "skipped": len(rows) - len(updates), "reason": "ok"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill adj_factor for A-share ETFs")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--resume", action="store_true", help="Resume from progress file")
    parser.add_argument("--progress-file", default=DEFAULT_PROGRESS_FILE)
    parser.add_argument("--limit", type=int, default=None, help="Process at most N ETFs")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Commit every N ETFs")
    parser.add_argument("--database-url", default=None, help="Override DATABASE_URL")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url

    completed = _load_progress(args.progress_file) if args.resume else set()
    db = SessionLocal()
    provider = TushareProvider()
    try:
        etfs = (
            db.query(ETFInfo.code)
            .filter(ETFInfo.market == "A股")
            .filter(ETFInfo.instrument_type == "ETF")
            .order_by(ETFInfo.code)
            .all()
        )
        codes = [e.code for e in etfs]
        if args.limit:
            codes = codes[: args.limit]

        total = len(codes)
        logger.info("Total A-share ETFs to process: %d (already completed: %d)", total, len(completed))

        stats = {
            "total": total,
            "completed": 0,
            "updated_rows": 0,
            "skipped_rows": 0,
            "started_at": datetime.utcnow().isoformat(),
        }

        for idx, code in enumerate(codes, start=1):
            if code in completed:
                logger.info("[%d/%d] Skipping %s (already completed)", idx, total, code)
                continue

            logger.info("[%d/%d] Processing %s", idx, total, code)
            try:
                result = backfill_code(db, provider, code, dry_run=args.dry_run)
                stats["completed"] += 1
                stats["updated_rows"] += result["updated"]
                stats["skipped_rows"] += result["skipped"]
                completed.add(code)
                logger.info(
                    "[%d/%d] %s -> updated=%d skipped=%d reason=%s",
                    idx, total, code, result["updated"], result["skipped"], result["reason"],
                )
            except Exception as exc:
                logger.exception("[%d/%d] Failed to process %s: %s", idx, total, code, exc)
                _save_progress(args.progress_file, completed, stats)
                raise

            if idx % args.batch_size == 0:
                _save_progress(args.progress_file, completed, stats)
                logger.info("Progress saved: %d/%d ETFs processed", len(completed), total)

            time.sleep(API_DELAY)

        stats["finished_at"] = datetime.utcnow().isoformat()
        _save_progress(args.progress_file, completed, stats)
        logger.info("Done. Final stats: %s", stats)
    finally:
        db.close()


if __name__ == "__main__":
    main()
