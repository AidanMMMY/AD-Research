"""One-off script: backfill GICS sector & industry for existing A-share stocks.

Reads the ``category`` column (CSRC industry name from Tushare) for every
``instrument_type='STOCK'`` / ``market='A股'`` row in ``etf_info``,
maps it to GICS via ``map_industry()``, and writes the result into the
``sector`` and ``industry`` columns.

Usage
-----
.. code-block:: bash

    python -m app.scripts.backfill_a_share_industry
"""

import logging
import sys

from app.core.database import SessionLocal
from app.data.indicators.a_share_industry_mapping import map_industry
from app.models.etf import ETFInfo

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

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
        unknown_industries: set[str] = set()

        for stock in stocks:
            sector, industry = map_industry(stock.category)
            if sector is not None:
                stock.sector = sector
                stock.industry = industry
                updated += 1
            else:
                skipped += 1
                if stock.category:
                    unknown_industries.add(stock.category)

        db.commit()
        logger.info("Updated %d stocks with GICS sector/industry", updated)
        logger.info("Skipped %d stocks (unrecognised industry)", skipped)

        if unknown_industries:
            logger.warning(
                "Unrecognised CSRC industries (%d): %s",
                len(unknown_industries),
                ", ".join(sorted(unknown_industries)),
            )

    except Exception:
        logger.exception("Backfill failed")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
