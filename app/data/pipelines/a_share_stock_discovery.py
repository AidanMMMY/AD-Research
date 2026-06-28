"""A-Share Individual Stock Discovery Pipeline.

Discovers and registers all China A-share individual stocks into the
unified etf_info instrument table with instrument_type="STOCK".

Uses TushareProvider to fetch the complete A-share stock list
(Shanghai, Shenzhen, Beijing exchanges).

Scheduled to run weekly (Monday 01:00 Beijing time).
"""

import logging
from datetime import date, datetime

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.data.indicators.a_share_industry_mapping import map_industry
from app.data.pipelines.base import ETLPipeline, ETLResult
from app.data.providers.tushare_provider import TushareProvider
from app.models.etf import ETFInfo

logger = logging.getLogger(__name__)


class AShareStockDiscoveryPipeline(ETLPipeline):
    """Pipeline that discovers A-share individual stocks and registers them
    in the unified etf_info instrument table.

    Fetches the full A-share stock list from Tushare stock_basic across
    SSE, SZSE, and BSE, then upserts into etf_info with
    instrument_type="STOCK" and market="A股".

    Weekly job — the stock universe changes infrequently.
    """

    job_name = "a_share_stock_discovery"

    def __init__(self, db: Session) -> None:
        provider = TushareProvider()
        super().__init__(provider=provider, db=db)

    def run(self) -> ETLResult:
        """Override base run() to skip price-bar validation.

        Discovery produces instrument metadata, not OHLCV bars.
        """
        result = ETLResult()
        self._create_log()

        try:
            raw_df = self.extract()
            if raw_df.empty:
                result.warnings.append("Extract returned empty DataFrame")

            records = self.load(raw_df)
            result.records = records
            result.success = True
            self._update_log(status="success", records=records)
            logger.info("AShareStockDiscoveryPipeline: Loaded %d stocks", records)

        except Exception as exc:
            error_msg = str(exc)
            result.success = False
            result.error = error_msg
            self._update_log(status="failed", error=error_msg)
            logger.error("AShareStockDiscoveryPipeline failed: %s", error_msg)

        return result

    def extract(self) -> pd.DataFrame:
        """Fetch A-share stock list from Tushare.

        Returns DataFrame with columns: code, name, exchange, market,
        currency, instrument_type, category (industry), inception_date, status
        """

        provider = TushareProvider()
        stocks = provider.fetch_etf_list()

        if not stocks:
            logger.warning("AShareStockDiscoveryPipeline: Tushare returned empty stock list")
            return pd.DataFrame()

        logger.info(
            "AShareStockDiscoveryPipeline: Fetched %d A-share stocks", len(stocks)
        )

        rows = []
        for stock in stocks:
            sector, gics_industry = map_industry(stock.category)
            rows.append(
                {
                    "code": stock.code,
                    "name": stock.name,
                    "exchange": stock.exchange,
                    "market": stock.market or "A股",
                    "currency": "CNY",
                    "instrument_type": "STOCK",
                    "category": stock.category,  # CSRC industry from Tushare
                    "sector": sector,             # GICS sector (mapped)
                    "industry": gics_industry,    # GICS industry (mapped)
                    "inception_date": stock.inception_date,
                    "status": "active",
                }
            )

        return pd.DataFrame(rows)

    def load(self, data: pd.DataFrame) -> int:
        """Upsert stock records into etf_info.

        Uses ON CONFLICT DO UPDATE to refresh names, exchanges, industry,
        and status while preserving any existing data.
        """

        if data.empty:
            return 0

        records = []
        for _, row in data.iterrows():
            inception_date_val = row.get("inception_date")
            if isinstance(inception_date_val, date):
                inception_date_val = inception_date_val.isoformat()

            record = {
                "code": str(row["code"]),
                "name": str(row["name"]),
                "exchange": str(row.get("exchange", "")) if row.get("exchange") else None,
                "market": str(row.get("market", "A股")),
                "currency": str(row.get("currency", "CNY")),
                "instrument_type": "STOCK",
                "category": str(row["category"]) if row.get("category") else None,
                "sector": str(row["sector"]) if row.get("sector") else None,
                "industry": str(row["industry"]) if row.get("industry") else None,
                "inception_date": inception_date_val,
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
                    "category": insert(ETFInfo).excluded.category,
                    "sector": insert(ETFInfo).excluded.sector,
                    "industry": insert(ETFInfo).excluded.industry,
                    "status": insert(ETFInfo).excluded.status,
                    "instrument_type": insert(ETFInfo).excluded.instrument_type,
                    "inception_date": insert(ETFInfo).excluded.inception_date,
                    "updated_at": insert(ETFInfo).excluded.updated_at,
                },
            )
        )

        self.db.execute(stmt)
        self.db.commit()

        new_count = len(records)
        logger.info("AShareStockDiscoveryPipeline: Upserted %d A-share stocks", new_count)
        return new_count
