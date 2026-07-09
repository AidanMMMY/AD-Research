#!/usr/bin/env python3
"""Backfill ``listing_market`` and ``board`` for A-share instruments in ``etf_info``.

Pure SQL-free derivation — the values are computed locally from the
``code`` prefix using the same helpers as the Tushare provider, so the
script needs no network access and is fully idempotent.

Mapping:
  * 60xxxx.SH / 00xxxx.SZ -> listing_market = 上海/深圳, board = 主板
  * 30xxxx.SZ             -> listing_market = 深圳, board = 创业板
  * 68xxxx.SH             -> listing_market = 上海, board = 科创板
  * 8xxxxx.BJ / 92xxxx.BJ / 43xxxx.BJ -> listing_market = 北京, board = 北交所
  * other A-share codes (default)       -> listing_market = 上海/深圳/北京, board = 主板

Usage inside backend container:
    cd /app && PYTHONPATH=/app python3 scripts/backfill_ashare_listing_market_and_board.py

Dry run:
    cd /app && PYTHONPATH=/app python3 scripts/backfill_ashare_listing_market_and_board.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy.orm import Session

# Make app imports work when script is run from repo root inside container.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

from app.core.database import SessionLocal  # noqa: E402
from app.data.providers.tushare_provider import (  # noqa: E402
    _derive_listing_market,
    derive_board,
)
from app.models.etf import ETFInfo  # noqa: E402

logger = logging.getLogger(__name__)


def _is_a_share(etf: ETFInfo) -> bool:
    """Return True if the row represents an A-share instrument.

    Matches both ``market="A股"`` (A-share stocks) and any code whose
    suffix is SH/SZ/BJ so the script is also useful for ETF rows that
    were registered before the market column was filled in.
    """
    if etf.market == "A股":
        return True
    code = etf.code or ""
    return code.endswith((".SH", ".SZ", ".BJ"))


def backfill(db: Session, *, dry_run: bool = False) -> tuple[int, int]:
    """Iterate every A-share row, derive + update ``listing_market``/``board``.

    Returns ``(updated, total)`` so the caller can log the outcome.
    Rows whose existing values already match the derived values are
    skipped to keep the run cheap when nothing changed.
    """
    rows = db.query(ETFInfo).all()
    a_share_rows = [r for r in rows if _is_a_share(r)]
    logger.info(
        "Found %d A-share rows out of %d total", len(a_share_rows), len(rows)
    )

    updated = 0
    for row in a_share_rows:
        new_listing_market = _derive_listing_market(row.code)
        new_board = derive_board(row.code)
        if row.listing_market == new_listing_market and row.board == new_board:
            continue
        if dry_run:
            logger.info(
                "[dry-run] %s -> listing_market=%s board=%s",
                row.code, new_listing_market, new_board,
            )
            updated += 1
            continue
        row.listing_market = new_listing_market
        row.board = new_board
        updated += 1

    if not dry_run and updated:
        db.commit()
        logger.info("Committed %d updates", updated)
    return updated, len(a_share_rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log the rows that would change without writing to the DB.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose logging.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    db = SessionLocal()
    try:
        updated, total = backfill(db, dry_run=args.dry_run)
        logger.info(
            "Backfill done: %d/%d A-share rows %s",
            updated,
            total,
            "would change" if args.dry_run else "updated",
        )
        return 0
    except Exception:
        logger.exception("Backfill failed")
        db.rollback()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())