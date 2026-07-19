#!/usr/bin/env python3
"""Backfill A-share cumulative adjustment factor history from Tushare.

Fetches the full-history ``adj_factor`` for every active A-share instrument
and writes it to ``adj_factor_history``. For backwards compatibility the
script also updates ``instrument_daily_bar.adj_factor`` for matching rows.

Usage (inside container or with PYTHONPATH set):
    python -m app.scripts.backfill_a_share_adj_factor
    python -m app.scripts.backfill_a_share_adj_factor --codes 600519.SH,000001.SZ --dry-run
    python -m app.scripts.backfill_a_share_adj_factor --no-update-daily-bar
"""

import argparse
import logging
import sys
from typing import Any

import pandas as pd
from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.data.providers.tushare_provider import TushareProvider
from app.models.etf import AdjFactorHistory, ETFInfo, InstrumentDailyBar

logger = logging.getLogger("backfill_a_share_adj_factor")


def backfill_adj_factor(
    db: Session,
    codes: list[str] | None = None,
    update_daily_bar: bool = True,
    dry_run: bool = False,
    chunk_size: int = 5000,
    batch_size: int = 500,
) -> dict[str, Any]:
    """Fetch full-history adj_factor from Tushare and upsert into storage.

    Uses Tushare's batch ``ts_code`` support (comma-separated codes) so the
    ~6,000 A-share stocks with local bars can be covered in a dozen API calls
    instead of thousands.

    Args:
        db: SQLAlchemy session.
        codes: Optional whitelist of instrument codes. When omitted, all active
            A-share instruments are processed.
        update_daily_bar: If True, also update ``instrument_daily_bar.adj_factor``
            for rows that exist in the backfill result.
        dry_run: If True, count records but do not write to the database.
        chunk_size: Bulk upsert chunk size.
        batch_size: Number of instruments to request from Tushare per API call.

    Returns:
        Dict with keys ``adj_factor_history_records``, ``daily_bar_updated``,
        and ``errors``.
    """
    provider = TushareProvider()

    query = (
        db.query(ETFInfo.code)
        .filter(ETFInfo.market == "A股")
        .filter(ETFInfo.status == "active")
    )
    if codes:
        query = query.filter(ETFInfo.code.in_(codes))
    all_codes = [row[0] for row in query.order_by(ETFInfo.code).all()]

    logger.info("Found %d active A-share instruments to process", len(all_codes))
    if not all_codes:
        return {
            "adj_factor_history_records": 0,
            "daily_bar_updated": 0,
            "errors": 0,
        }

    # Determine the local bar date range for each code. Codes without local
    # bars are dropped from the Tushare requests entirely.
    date_ranges = (
        db.query(
            InstrumentDailyBar.etf_code,
            func.min(InstrumentDailyBar.trade_date).label("min_date"),
            func.max(InstrumentDailyBar.trade_date).label("max_date"),
        )
        .filter(InstrumentDailyBar.etf_code.in_(all_codes))
        .group_by(InstrumentDailyBar.etf_code)
        .all()
    )
    meta_by_code: dict[str, tuple[Any, Any]] = {
        row.etf_code: (row.min_date, row.max_date) for row in date_ranges
    }

    codes_with_bars = [c for c in all_codes if c in meta_by_code]
    skipped = len(all_codes) - len(codes_with_bars)
    if skipped:
        logger.info("%d instruments have no local bars and will be skipped", skipped)
    if not codes_with_bars:
        logger.warning("No local bars found for any instrument; nothing to backfill")
        return {
            "adj_factor_history_records": 0,
            "daily_bar_updated": 0,
            "errors": 0,
        }

    # Use the widest date range across all requested bars. Tushare returns the
    # available history within the range for each code; we filter to actual
    # local bars when updating ``instrument_daily_bar``.
    global_min_date = min(m[0] for m in meta_by_code.values())
    global_max_date = max(m[1] for m in meta_by_code.values())
    logger.info(
        "Global bar date range: %s to %s; processing in batches of %d",
        global_min_date,
        global_max_date,
        batch_size,
    )

    total_history_records = 0
    total_daily_bar_updated = 0
    errors: list[str] = []

    for batch_index in range(0, len(codes_with_bars), batch_size):
        batch = codes_with_bars[batch_index : batch_index + batch_size]
        label = f"batch {batch_index // batch_size + 1}/{(len(codes_with_bars) - 1) // batch_size + 1}"
        try:
            df = provider.fetch_adj_factor(
                ts_code=",".join(batch),
                start_date=global_min_date,
                end_date=global_max_date,
            )
        except Exception as exc:
            logger.warning("%s: failed to fetch adj_factor: %s", label, exc)
            errors.append(f"{label}: {exc}")
            continue

        if df is None or df.empty:
            logger.info("%s: no adj_factor data", label)
            continue

        records: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            trade_date = row.get("trade_date")
            af = row.get("adj_factor")
            etf_code = row.get("etf_code")
            if etf_code and trade_date and pd.notna(af):
                records.append(
                    {
                        "etf_code": etf_code,
                        "trade_date": trade_date,
                        "adj_factor": float(af),
                        "source": "tushare",
                    }
                )

        logger.info(
            "%s: fetched %d adj_factor rows for %d instruments",
            label,
            len(records),
            df["etf_code"].nunique() if "etf_code" in df.columns else 0,
        )

        # Upsert into the authoritative history table per batch so memory
        # usage stays bounded even for the full market.
        total_history_records += _upsert_adj_factor_history(
            db, records, dry_run, chunk_size
        )

        # Mirror the latest values back to instrument_daily_bar for backwards
        # compatibility with existing indicator calculations.
        if update_daily_bar:
            total_daily_bar_updated += _update_daily_bar_adj_factor(
                db, records, dry_run, chunk_size
            )

    logger.info(
        "Backfill summary: adj_factor_history=%d, daily_bar_updated=%d, errors=%d",
        total_history_records,
        total_daily_bar_updated,
        len(errors),
    )
    if errors:
        logger.warning("Errors encountered (%d):", len(errors))
        for err in errors[:10]:
            logger.warning("  %s", err)

    return {
        "adj_factor_history_records": total_history_records,
        "daily_bar_updated": total_daily_bar_updated,
        "errors": len(errors),
    }


def _upsert_adj_factor_history(
    db: Session,
    records: list[dict[str, Any]],
    dry_run: bool,
    chunk_size: int,
) -> int:
    """Bulk upsert ``records`` into ``adj_factor_history``."""
    if not records:
        return 0

    total = 0
    for i in range(0, len(records), chunk_size):
        chunk = records[i : i + chunk_size]
        if dry_run:
            total += len(chunk)
            continue

        stmt = (
            insert(AdjFactorHistory)
            .values(chunk)
            .on_conflict_do_update(
                index_elements=["etf_code", "trade_date"],
                set_={
                    "adj_factor": insert(AdjFactorHistory).excluded.adj_factor,
                    "source": insert(AdjFactorHistory).excluded.source,
                    "updated_at": func.now(),
                },
            )
        )
        result = db.execute(stmt)
        db.commit()
        total += result.rowcount

    return total


def _update_daily_bar_adj_factor(
    db: Session,
    records: list[dict[str, Any]],
    dry_run: bool,
    chunk_size: int,
) -> int:
    """Bulk update ``instrument_daily_bar.adj_factor`` from ``records``."""
    if not records:
        return 0

    total = 0
    for i in range(0, len(records), chunk_size):
        chunk = records[i : i + chunk_size]
        if dry_run:
            total += len(chunk)
            continue

        values = ", ".join(
            f"('{r['etf_code']}', '{r['trade_date'].isoformat()}', {r['adj_factor']})"
            for r in chunk
        )
        update_sql = text(
            f"""
            UPDATE instrument_daily_bar AS t
            SET adj_factor = v.adj_factor
            FROM (VALUES {values}) AS v(etf_code, trade_date, adj_factor)
            WHERE t.etf_code = v.etf_code
              AND t.trade_date = v.trade_date::date
            """
        )
        try:
            result = db.execute(update_sql)
            db.commit()
            total += result.rowcount
        except Exception:
            db.rollback()
            logger.exception("Bulk update of instrument_daily_bar.adj_factor failed")
            raise

    return total


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill A-share adj_factor history from Tushare"
    )
    parser.add_argument(
        "--codes",
        type=str,
        help="Comma-separated instrument codes (e.g. 600519.SH,000001.SZ)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count records without writing to the database",
    )
    parser.add_argument(
        "--no-update-daily-bar",
        dest="update_daily_bar",
        action="store_false",
        default=True,
        help="Skip updating instrument_daily_bar.adj_factor",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=5000,
        help="Bulk upsert chunk size (default 5000)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Number of instruments per Tushare API call (default 500)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    codes = (
        [c.strip() for c in args.codes.split(",") if c.strip()]
        if args.codes
        else None
    )

    db = SessionLocal()
    try:
        result = backfill_adj_factor(
            db,
            codes=codes,
            update_daily_bar=args.update_daily_bar,
            dry_run=args.dry_run,
            chunk_size=args.chunk_size,
            batch_size=args.batch_size,
        )
        return 0 if result["errors"] == 0 else 1
    except Exception:
        logger.exception("Backfill failed")
        db.rollback()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
