"""A-Share Individual Stock Fundamental ETL Pipeline.

Fetches daily valuation and market data (PE, PB, market cap, turnover, etc.)
from Tushare daily_basic endpoint and upserts into ``stock_fundamental``.

Scheduled at 16:30 daily (after the daily bar pipeline completes).
"""

import logging
from datetime import date, timedelta

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.data.pipelines.base import ETLPipeline, ETLResult
from app.data.providers.tushare_provider import TushareProvider
from app.models.etf import ETFInfo, StockFundamental

logger = logging.getLogger(__name__)


class AStockFundamentalPipeline(ETLPipeline):
    """ETL pipeline for A-share stock daily valuation & market data.

    Sources from Tushare daily_basic which provides PE, PB, market cap,
    turnover rate (free float), volume ratio, and share counts for
    all listed A-share stocks.
    """

    job_name = "a_stock_fundamental"

    def __init__(self, db: Session, target_date: date | None = None) -> None:
        provider = TushareProvider()
        super().__init__(provider=provider, db=db)
        self.target_date = target_date

    def run(self) -> ETLResult:
        """Override base run() to skip price-bar validation.

        Fundamental data (PE, PB, market cap) is not OHLCV data.
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
            logger.info("AStockFundamentalPipeline: Loaded %d records", records)

        except Exception as exc:
            error_msg = str(exc)
            result.success = False
            result.error = error_msg
            self._update_log(status="failed", error=error_msg)
            logger.error("AStockFundamentalPipeline failed: %s", error_msg)

        return result

    def extract(self) -> pd.DataFrame:
        """Fetch daily_basic for the target date (or yesterday).

        Uses the market-wide daily_basic(trade_date=...) endpoint which
        returns ALL stocks in a single API call — the most efficient way
        to get valuation data for the entire A-share market.
        """

        target_date = self.target_date or (date.today() - timedelta(days=1))
        target_date_str = target_date.strftime("%Y%m%d")

        logger.info("AStockFundamentalPipeline: Fetching daily_basic for %s", target_date)

        provider = TushareProvider()
        df = provider.fetch_daily_basic(trade_date=target_date)

        if df is None or df.empty:
            logger.warning(
                "AStockFundamentalPipeline: Empty daily_basic for %s", target_date
            )
            return pd.DataFrame()

        logger.info(
            "AStockFundamentalPipeline: Got %d rows from daily_basic for %s",
            len(df), target_date,
        )
        return df

    def load(self, data: pd.DataFrame) -> int:
        """Upsert fundamental records into ``stock_fundamental``.

        Only inserts records for stocks that already exist in etf_info
        (registered by the discovery pipeline).
        """

        if data.empty:
            return 0

        # Filter to known instrument codes to avoid FK violations
        known_codes = set(
            row[0] for row in
            self.db.query(ETFInfo.code)
            .filter(ETFInfo.market == "A股", ETFInfo.instrument_type == "STOCK")
            .all()
        )
        data = data[data["etf_code"].isin(known_codes)].copy()
        if data.empty:
            logger.warning("AStockFundamentalPipeline: No data after filtering to known codes")
            return 0

        # Tushare daily_basic returns: ts_code, trade_date, pe_ttm, pb, total_mv,
        # circ_mv, turnover_rate_f, volume_ratio, total_share, float_share, free_share
        field_map: list[tuple[str, str]] = [
            ("etf_code", "stock_code"),
            ("trade_date", "trade_date"),
            ("pe_ttm", "pe_ttm"),
            ("pb", "pb"),
            ("total_mv", "total_mv"),
            ("circ_mv", "circ_mv"),
            ("turnover_rate_f", "turnover_rate_f"),
            ("volume_ratio", "volume_ratio"),
            ("total_share", "total_share"),
            ("float_share", "float_share"),
            ("free_share", "free_share"),
        ]

        records = []
        for _, row in data.iterrows():
            record = {}
            for src_col, dst_col in field_map:
                val = row.get(src_col)
                # Convert pandas/numpy NaN/NaT to None for SQLAlchemy compatibility.
                # pd.isna() handles float NaN, np.nan, None, NaT transparently.
                if val is None or pd.isna(val):
                    record[dst_col] = None
                else:
                    record[dst_col] = val
            # All records must have the same keys for multi-row INSERT
            if record.get("stock_code") and record.get("trade_date"):
                records.append(record)

        if not records:
            return 0

        stmt = (
            insert(StockFundamental)
            .values(records)
            .on_conflict_do_update(
                index_elements=["stock_code", "trade_date"],
                set_={
                    "pe_ttm": insert(StockFundamental).excluded.pe_ttm,
                    "pb": insert(StockFundamental).excluded.pb,
                    "total_mv": insert(StockFundamental).excluded.total_mv,
                    "circ_mv": insert(StockFundamental).excluded.circ_mv,
                    "turnover_rate_f": insert(StockFundamental).excluded.turnover_rate_f,
                    "volume_ratio": insert(StockFundamental).excluded.volume_ratio,
                    "total_share": insert(StockFundamental).excluded.total_share,
                    "float_share": insert(StockFundamental).excluded.float_share,
                    "free_share": insert(StockFundamental).excluded.free_share,
                },
            )
        )

        self.db.execute(stmt)
        self.db.commit()

        logger.info("AStockFundamentalPipeline: Upserted %d records", len(records))
        return len(records)
