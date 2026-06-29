"""US ETF discovery pipeline.

Discovers and registers curated US ETFs from Finnhub's hard-coded list
into the etf_info table with instrument_type="ETF" and market="US".

The list includes ~70 highly liquid US ETFs across broad market, sector,
factor, bond, commodity, and thematic categories.  This pipeline keeps
categories in sync so that downstream filters (e.g. the ETF list page)
can show meaningful category choices for US ETFs.

Scheduled to run weekly (Sunday 01:00 Beijing time), before the US stock
discovery job.
"""

import logging

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.data.pipelines.base import ETLPipeline, ETLResult
from app.data.providers.finnhub_provider import FinnhubProvider
from app.models.etf import ETFInfo

logger = logging.getLogger(__name__)


class USEtfDiscoveryPipeline(ETLPipeline):
    """Pipeline that discovers curated US ETFs and registers them
    in the unified etf_info instrument table.

    Uses FinnhubProvider.fetch_etf_list() which returns a hard-coded
    list of liquid US ETFs with category metadata.  The pipeline
    upserts these records so that category changes are propagated
    while preserving existing price/indicator data.

    Weekly job — the curated list changes infrequently.
    """

    job_name = "us_etf_discovery"

    def __init__(self, db: Session) -> None:
        provider = FinnhubProvider()
        super().__init__(provider=provider, db=db)

    def run(self) -> ETLResult:
        """Override base run() to skip OHLCV-specific validation.

        Discovery produces instrument metadata, not price bars, so the
        standard four-layer validator does not apply.
        """
        result = ETLResult()
        self._create_log()

        try:
            data = self.extract()
            if data.empty:
                result.warnings.append("Extract returned empty DataFrame")

            loaded = self.load(data)
            result.records = loaded
            result.success = True
            self._update_log(status="success", records=loaded)
            logger.info("USEtfDiscoveryPipeline: Loaded %d US ETFs", loaded)

        except Exception as exc:
            error_msg = str(exc)
            result.success = False
            result.error = error_msg
            self._update_log(status="failed", error=error_msg)
            logger.error("USEtfDiscoveryPipeline failed: %s", error_msg)

        return result

    def extract(self) -> pd.DataFrame:
        """Fetch the curated US ETF list and return as a DataFrame."""
        etfs = self.provider.fetch_etf_list()
        if not etfs:
            logger.warning("USEtfDiscoveryPipeline: provider returned empty ETF list")
            return pd.DataFrame()

        rows = []
        for etf in etfs:
            rows.append(
                {
                    "code": etf.code,
                    "name": etf.name,
                    "market": etf.market or "US",
                    "exchange": etf.exchange,
                    "category": etf.category,
                    "currency": etf.currency or "USD",
                    "instrument_type": "ETF",
                    "status": "active",
                }
            )

        logger.info("USEtfDiscoveryPipeline: Fetched %d US ETFs", len(rows))
        return pd.DataFrame(rows)

    def load(self, data: pd.DataFrame) -> int:
        """Upsert US ETF records into etf_info.

        Uses ON CONFLICT DO UPDATE to refresh names, exchanges, categories,
        and instrument_type while preserving existing indicator/bar data.
        """
        if data.empty:
            return 0

        records = data.to_dict("records")
        stmt = (
            insert(ETFInfo)
            .values(records)
            .on_conflict_do_update(
                index_elements=["code"],
                set_={
                    "name": insert(ETFInfo).excluded.name,
                    "exchange": insert(ETFInfo).excluded.exchange,
                    "category": insert(ETFInfo).excluded.category,
                    "market": insert(ETFInfo).excluded.market,
                    "currency": insert(ETFInfo).excluded.currency,
                    "instrument_type": insert(ETFInfo).excluded.instrument_type,
                    "status": insert(ETFInfo).excluded.status,
                    "updated_at": insert(ETFInfo).excluded.updated_at,
                },
            )
        )
        self.db.execute(stmt)
        self.db.commit()

        logger.info("USEtfDiscoveryPipeline: Upserted %d US ETFs", len(records))
        return len(records)
