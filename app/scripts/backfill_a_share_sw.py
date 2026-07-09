"""Backfill 申万一级行业 (SW L1) for existing A-share stocks.

By default this uses the OFFLINE static CSRC→SW map: it reads the
``category`` column (CSRC industry name from Tushare) for every
``instrument_type='STOCK'`` / ``market='A股'`` row in ``etf_info`` and
writes the resolved ``sw_l1`` / ``sw_l1_code``.

Pass ``--from-tushare`` to instead pull authoritative per-stock membership
from Tushare ``index_classify`` + ``index_member`` (requires elevated
积分). On any Tushare failure the script falls back to the static map so a
partial run still leaves the columns populated.

Usage
-----
.. code-block:: bash

    python -m app.scripts.backfill_a_share_sw               # offline map
    python -m app.scripts.backfill_a_share_sw --from-tushare  # Tushare
"""

import argparse
import logging
import sys

from app.core.database import SessionLocal
from app.data.indicators.a_share_sw_mapping import map_csrc_to_sw
from app.models.etf import ETFInfo

logger = logging.getLogger(__name__)


def _load_tushare_membership() -> dict[str, tuple[str, str]]:
    """Fetch authoritative SW L1 membership from Tushare (or {} on failure)."""
    try:
        from app.data.providers.tushare_provider import TushareProvider

        provider = TushareProvider()
        return provider.fetch_sw_l1_membership()
    except Exception:
        logger.exception(
            "Tushare SW membership fetch failed; falling back to CSRC map"
        )
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill SW L1 for A-shares")
    parser.add_argument(
        "--from-tushare",
        action="store_true",
        help="Use Tushare index_classify/index_member (authoritative)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    membership: dict[str, tuple[str, str]] = {}
    if args.from_tushare:
        membership = _load_tushare_membership()
        logger.info("Loaded %d Tushare SW memberships", len(membership))

    db = SessionLocal()
    try:
        stocks = (
            db.query(ETFInfo)
            .filter(
                ETFInfo.market == "A股",
                ETFInfo.instrument_type == "STOCK",
            )
            .all()
        )
        logger.info("Found %d A-share stocks to process", len(stocks))

        updated = 0
        skipped = 0
        from_tushare = 0
        from_map = 0
        unknown: set[str] = set()

        for stock in stocks:
            sw_name: str | None = None
            sw_code: str | None = None

            hit = membership.get(stock.code)
            if hit is not None:
                sw_name, sw_code = hit
                from_tushare += 1
            else:
                sw_name, sw_code = map_csrc_to_sw(stock.category)
                if sw_name is not None:
                    from_map += 1

            if sw_name is not None:
                stock.sw_l1 = sw_name
                stock.sw_l1_code = sw_code
                updated += 1
            else:
                skipped += 1
                if stock.category:
                    unknown.add(stock.category)

        db.commit()
        logger.info(
            "Updated %d stocks (%d from Tushare, %d from CSRC map)",
            updated, from_tushare, from_map,
        )
        logger.info("Skipped %d stocks (unrecognised industry)", skipped)
        if unknown:
            logger.warning(
                "Unrecognised CSRC industries (%d): %s",
                len(unknown), ", ".join(sorted(unknown)),
            )
    except Exception:
        logger.exception("SW backfill failed")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
