"""US stock metadata enrichment pipeline.

Backfills missing sector/industry/category metadata for US individual
stocks from the public S&P 500 constituents CSV (which includes GICS
sector and sub-industry).  The CSV is free, requires no API key, and is
updated regularly.

Runs daily in small batches so that newly discovered US stocks or stocks
that missed sector data during discovery are eventually enriched.
"""

import logging

import pandas as pd
import requests
from sqlalchemy.orm import Session

from app.data.pipelines.base import ETLPipeline, ETLResult
from app.data.providers.base import DataProvider, ETFInfo, MarketHours
from app.models.etf import ETFInfo

logger = logging.getLogger(__name__)

# Public dataset with GICS sector / sub-industry for S&P 500 constituents.
_SP500_CSV_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/"
    "main/data/constituents.csv"
)

# Process a limited number of stocks per run to keep the job quick and
# avoid unnecessary load on the upstream dataset.
_DEFAULT_BATCH_SIZE = 200


class _CsvProvider(DataProvider):
    """Minimal concrete provider for the enrichment pipeline.

    The pipeline reads the public S&P 500 CSV directly; this provider is
    only used to satisfy the ETLPipeline base class constructor.
    """

    @property
    def name(self) -> str:
        return "sp500-csv"

    def fetch_etf_list(self) -> list[ETFInfo]:
        return []

    def fetch_daily_bars(self, codes, start_date, end_date):
        return pd.DataFrame()

    def fetch_realtime_quotes(self, codes):
        return []

    def get_market_hours(self, date):
        return MarketHours.OPEN


class USStockEnrichmentPipeline(ETLPipeline):
    """Enrich US stock metadata from the public S&P 500 CSV.

    Populates sector, industry, and category (mapped from sector) for
    US individual stocks that are missing this information.
    """

    job_name = "us_stock_enrichment"

    def __init__(self, db: Session, batch_size: int = _DEFAULT_BATCH_SIZE) -> None:
        super().__init__(provider=_CsvProvider(), db=db)
        self.batch_size = batch_size

    def run(self) -> ETLResult:
        """Override base run() to skip OHLCV-specific validation."""
        result = ETLResult()
        self._create_log()

        try:
            data = self.extract()
            if data.empty:
                result.warnings.append("No US stocks need enrichment")

            updated = self.load(data)
            result.records = updated
            result.success = True
            self._update_log(status="success", records=updated)
            logger.info(
                "USStockEnrichmentPipeline: Updated %d US stocks", updated
            )

        except Exception as exc:
            error_msg = str(exc)
            result.success = False
            result.error = error_msg
            self._update_log(status="failed", error=error_msg)
            logger.error("USStockEnrichmentPipeline failed: %s", error_msg)

        return result

    def _fetch_sector_lookup(self) -> dict[str, dict[str, str | None]]:
        """Download S&P 500 CSV and build a ticker-to-metadata lookup."""
        import requests

        resp = requests.get(_SP500_CSV_URL, timeout=30)
        resp.raise_for_status()
        df = pd.read_csv(pd.io.common.StringIO(resp.text))

        lookup: dict[str, dict[str, str | None]] = {}
        for _, row in df.iterrows():
            symbol = str(row.get("Symbol", "")).strip().upper()
            if not symbol:
                continue
            lookup[f"{symbol}.US"] = {
                "sector": str(row.get("GICS Sector", "")).strip() or None,
                "industry": str(row.get("GICS Sub-Industry", "")).strip() or None,
            }
        return lookup

    def extract(self) -> pd.DataFrame:
        """Find US stocks missing sector/category and return metadata rows."""
        lookup = self._fetch_sector_lookup()

        stocks = (
            self.db.query(ETFInfo)
            .filter(ETFInfo.market == "US")
            .filter(ETFInfo.instrument_type == "STOCK")
            .filter(
                (ETFInfo.sector.is_(None))
                | (ETFInfo.sector == "")
                | (ETFInfo.category.is_(None))
                | (ETFInfo.category == "")
            )
            .order_by(ETFInfo.code)
            .limit(self.batch_size)
            .all()
        )

        if not stocks:
            logger.info("USStockEnrichmentPipeline: No US stocks need enrichment")
            return pd.DataFrame()

        rows = []
        for stock in stocks:
            meta = lookup.get(stock.code)
            if not meta:
                continue
            sector = meta.get("sector")
            if not sector:
                continue
            rows.append(
                {
                    "code": stock.code,
                    "sector": sector,
                    "industry": meta.get("industry"),
                    "category": sector,
                }
            )

        logger.info(
            "USStockEnrichmentPipeline: Enriching %d/%d stocks",
            len(rows),
            len(stocks),
        )
        return pd.DataFrame(rows)

    def load(self, data: pd.DataFrame) -> int:
        """Update etf_info with sector/industry/category."""
        if data.empty:
            return 0

        updated = 0
        for _, row in data.iterrows():
            code = row.get("code")
            if not code:
                continue

            info = self.db.query(ETFInfo).filter(ETFInfo.code == code).first()
            if info is None:
                continue

            changed = False
            if row.get("sector") and (not info.sector or info.sector == ""):
                info.sector = row["sector"]
                changed = True
            if row.get("industry") and (not info.industry or info.industry == ""):
                info.industry = row["industry"]
                changed = True
            if row.get("category") and (not info.category or info.category == ""):
                info.category = row["category"]
                changed = True

            if changed:
                updated += 1

        self.db.commit()
        logger.info("USStockEnrichmentPipeline: Updated %d rows", updated)
        return updated
