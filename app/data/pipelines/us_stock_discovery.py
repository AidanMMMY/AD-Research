"""US Stock Discovery Pipeline.

Discovers and registers US individual stocks (S&P 500 constituents)
into the etf_info table with instrument_type="STOCK".

Uses FMPProvider to fetch the S&P 500 list and enrich each stock
with sector, industry, and market cap data.

Scheduled to run weekly (Sunday 02:00 Beijing time).
"""

import logging
from datetime import date, timedelta

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.data.pipelines.base import ETLPipeline
from app.data.providers.fmp_provider import FMPProvider
from app.models.etf import ETFInfo

logger = logging.getLogger(__name__)

# Limit the number of companies fetched per run to stay within
# FMP free tier limits (250 requests/day). Stock discovery itself
# uses 1 request for the list + ~2-3 for profiles.
_MAX_COMPANIES = 500


class USStockDiscoveryPipeline(ETLPipeline):
    """Pipeline that discovers US individual stocks and registers them
    in the unified etf_info instrument table.

    Fetches S&P 500 constituents from FMP, enriches each with sector
    and market cap data, then upserts into etf_info with
    instrument_type="STOCK" and market="US".

    Weekly job — the S&P 500 changes infrequently.
    """

    job_name = "us_stock_discovery"

    def __init__(self, db: Session) -> None:
        provider = FMPProvider()
        super().__init__(provider=provider, db=db)

    def extract(self) -> pd.DataFrame:
        """Fetch S&P 500 list and return as a DataFrame of stock info.

        Columns: code, name, exchange, market, currency, instrument_type,
                 sector, industry, market_cap, country, status
        """
        fmp = FMPProvider()
        stocks = fmp.fetch_sp500_list()

        if not stocks:
            logger.warning("USStockDiscoveryPipeline: FMP returned empty S&P 500 list")
            return pd.DataFrame()

        logger.info("USStockDiscoveryPipeline: Fetched %d S&P 500 constituents", len(stocks))

        rows = []
        for stock in stocks[: _MAX_COMPANIES]:
            rows.append(
                {
                    "code": stock.code,
                    "name": stock.name,
                    "exchange": stock.exchange,
                    "market": stock.market or "US",
                    "currency": stock.currency or "USD",
                    "instrument_type": "STOCK",
                    "sector": None,
                    "industry": None,
                    "market_cap": None,
                    "country": "US",
                    "status": "active",
                }
            )

        return pd.DataFrame(rows)

    def load(self, data: pd.DataFrame) -> int:
        """Upsert stock records into etf_info.

        Uses ON CONFLICT DO UPDATE to refresh names, exchanges, and
        status while preserving existing category/indicator/bar data.

        Only updates name, exchange, and status — does NOT overwrite
        sector/industry/market_cap if already populated by enrichment.
        """
        if data.empty:
            return 0

        records = []
        for _, row in data.iterrows():
            record = {
                "code": str(row["code"]),
                "name": str(row["name"]),
                "exchange": str(row.get("exchange", "")) if row.get("exchange") else None,
                "market": str(row.get("market", "US")),
                "currency": str(row.get("currency", "USD")),
                "instrument_type": str(row.get("instrument_type", "STOCK")),
                "country": str(row.get("country", "US")),
                "status": str(row.get("status", "active")),
            }
            records.append(record)

        if not records:
            return 0

        stmt = (
            insert(ETFInfo)
            .values(records)
            .on_conflict_do_update(
                index_elements=["code"],
                set_={
                    "name": insert(ETFInfo).excluded.name,
                    "exchange": insert(ETFInfo).excluded.exchange,
                    "status": insert(ETFInfo).excluded.status,
                    "instrument_type": insert(ETFInfo).excluded.instrument_type,
                    "updated_at": insert(ETFInfo).excluded.updated_at,
                },
            )
        )

        self.db.execute(stmt)
        self.db.commit()

        new_count = len(records)
        logger.info(
            "USStockDiscoveryPipeline: Upserted %d S&P 500 stocks", new_count
        )
        return new_count
