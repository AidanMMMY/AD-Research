#!/usr/bin/env python3
"""One-off unit fix for ETF holdings stored in 万股/万元.

Eastmoney F10 (``eastmoney_f10``) and Akshare (``akshare``) holdings
snapshots were persisted with ``shares`` in 万股 and ``market_value`` in
万元, while the Tushare source stores raw shares / yuan. The providers
have been fixed to multiply by 1e4 before insert; this script repairs the
rows already in the ``etf_holding`` table by multiplying ``shares`` and
``market_value`` by 1e4 for exactly those two sources.

Run it ONCE. Re-running would multiply again — the script therefore
refuses to apply unless ``--apply`` is passed, and the verification SQL
below should be checked before and after.

Usage inside backend container:
    cd /app && PYTHONPATH=/app python3 scripts/fix_etf_holdings_unit.py            # dry run
    cd /app && PYTHONPATH=/app python3 scripts/fix_etf_holdings_unit.py --apply    # write

Verification SQL (run before and after; row counts must match the
script's per-source/per-report_date breakdown):

    -- Rows in scope, grouped for cross-checking the script output
    SELECT source, snapshot_date, COUNT(*) AS rows,
           MIN(market_value) AS min_mv, MAX(market_value) AS max_mv
    FROM etf_holding
    WHERE source IN ('eastmoney_f10', 'akshare')
    GROUP BY source, snapshot_date
    ORDER BY source, snapshot_date;

    -- Sanity: after the fix, eastmoney/akshare magnitudes should be
    -- comparable to tushare rows for the same snapshot
    SELECT source, COUNT(*) AS rows,
           AVG(market_value) AS avg_mv, AVG(shares) AS avg_shares
    FROM etf_holding
    GROUP BY source
    ORDER BY source;
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import bindparam, text

# Make app imports work when script is run from repo root inside container.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

from app.core.database import SessionLocal

logger = logging.getLogger("fix_etf_holdings_unit")

SOURCES = ("eastmoney_f10", "akshare")

_BREAKDOWN_SQL = text(
    """
    SELECT source, snapshot_date, COUNT(*) AS rows
    FROM etf_holding
    WHERE source IN :sources
    GROUP BY source, snapshot_date
    ORDER BY source, snapshot_date
    """
).bindparams(bindparam("sources", expanding=True))

_UPDATE_SQL = text(
    """
    UPDATE etf_holding
    SET shares = shares * 1e4,
        market_value = market_value * 1e4
    WHERE source IN :sources
    """
).bindparams(bindparam("sources", expanding=True))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Multiply eastmoney_f10/akshare etf_holding rows by 1e4 (unit fix)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write the UPDATE. Without this flag the script is a dry run.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    with SessionLocal() as session:
        breakdown = session.execute(_BREAKDOWN_SQL, {"sources": SOURCES}).all()
        total = sum(row.rows for row in breakdown)
        logger.info("Rows in scope (source, snapshot_date, rows):")
        for row in breakdown:
            logger.info("  %s %s %d", row.source, row.snapshot_date, row.rows)
        logger.info("Total rows in scope: %d", total)

        if total == 0:
            logger.info("Nothing to do.")
            return 0

        if not args.apply:
            logger.info(
                "Dry run — re-run with --apply to multiply shares/market_value "
                "by 1e4 for these %d rows.",
                total,
            )
            return 0

        result = session.execute(_UPDATE_SQL, {"sources": SOURCES})
        session.commit()
        logger.info("Updated %d rows (shares/market_value × 1e4).", result.rowcount)
        logger.info(
            "Cross-check with the verification SQL in the script header — "
            "eastmoney_f10/akshare magnitudes should now match the tushare source."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
