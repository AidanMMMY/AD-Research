"""A-Share Individual Stock Daily ETL Pipeline.

Fetches daily OHLCV bars for all active China A-share individual stocks
and upserts them into the ``etf_daily_bar`` table.

Uses TushareProvider's daily() endpoint as the data source.

Scheduled at 16:00 daily (after A-share market close at 15:00 CST).
"""

import logging
from datetime import date, timedelta

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.cache import cache_invalidate_pattern
from app.data.pipelines.base import ETLPipeline
from app.data.providers.tushare_provider import TushareProvider
from app.models.etf import ETFDailyBar, ETFInfo

logger = logging.getLogger(__name__)


class AStockDailyPipeline(ETLPipeline):
    """ETL pipeline for A-share individual stock daily OHLCV bars."""

    job_name = "a_stock_daily_etl"

    def __init__(self, db: Session, target_date: date | None = None) -> None:
        provider = TushareProvider()
        super().__init__(provider=provider, db=db)
        self.target_date = target_date

    def extract(self) -> pd.DataFrame:
        """Fetch daily bars for active A-share individual stocks.

        By default fetches yesterday's bars (last complete trading day).
        If ``target_date`` is provided, fetches bars for that date instead
        (used for backfilling missed runs).
        """

        # 1. Query active A-share individual stocks from DB
        stocks = (
            self.db.query(ETFInfo)
            .filter(ETFInfo.market == "A股")
            .filter(ETFInfo.instrument_type == "STOCK")
            .filter(ETFInfo.status == "active")
            .all()
        )

        if not stocks:
            logger.warning("AStockDailyPipeline: No active A-share stocks found")
            return pd.DataFrame()

        codes = [s.code for s in stocks]
        self._expected_codes = codes
        logger.info("AStockDailyPipeline: Processing %d active A-share stocks", len(codes))

        # 2. Determine target trade date
        target_date = self.target_date or (date.today() - timedelta(days=1))

        # 3. Fetch daily bars (fetch a 7-day window to cover weekends/holidays)
        start_date = target_date - timedelta(days=7)
        end_date = target_date

        df = self.provider.fetch_daily_bars(codes, start_date, end_date)

        if df.empty:
            logger.info("AStockDailyPipeline: No bars found for %s", target_date)
            return df

        # 4. Keep only target date's data
        before = len(df)
        df = df[df["trade_date"] == target_date].copy()
        logger.info(
            "AStockDailyPipeline: Filtered %d→%d rows for target date %s",
            before, len(df), target_date,
        )

        return df

    def load(self, data: pd.DataFrame) -> int:
        """Upsert daily bar records into ``etf_daily_bar``.

        Uses PostgreSQL ON CONFLICT DO UPDATE for idempotent writes.
        The unique key is (etf_code, trade_date).
        """

        if data.empty:
            return 0

        records = []
        for _, row in data.iterrows():
            record = {
                "etf_code": row.get("etf_code"),
                "trade_date": row.get("trade_date"),
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume"),
                "amount": row.get("amount"),
                "pre_close": row.get("pre_close"),
                "change_pct": row.get("change_pct"),
                "turnover_rate": row.get("turnover_rate"),
            }
            # Drop None values so they don't overwrite existing data on conflict
            record = {k: v for k, v in record.items() if v is not None}
            records.append(record)

        if not records:
            return 0

        stmt = (
            insert(ETFDailyBar)
            .values(records)
            .on_conflict_do_update(
                index_elements=["etf_code", "trade_date"],
                set_={
                    "open": insert(ETFDailyBar).excluded.open,
                    "high": insert(ETFDailyBar).excluded.high,
                    "low": insert(ETFDailyBar).excluded.low,
                    "close": insert(ETFDailyBar).excluded.close,
                    "volume": insert(ETFDailyBar).excluded.volume,
                    "amount": insert(ETFDailyBar).excluded.amount,
                    "pre_close": insert(ETFDailyBar).excluded.pre_close,
                    "change_pct": insert(ETFDailyBar).excluded.change_pct,
                    "turnover_rate": insert(ETFDailyBar).excluded.turnover_rate,
                },
            )
        )

        self.db.execute(stmt)
        self.db.commit()

        # Invalidate caches that depend on daily bar data
        try:
            cache_invalidate_pattern("indicator:*")
            cache_invalidate_pattern("screen:*")
            cache_invalidate_pattern("etf:list:*")
        except Exception:
            logger.exception("Failed to invalidate caches after A-stock daily ETL")

        return len(records)
