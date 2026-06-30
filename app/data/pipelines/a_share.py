"""A-share ETF daily ETL pipeline.

Fetches daily OHLCV bars for all active China A-share ETFs and
upserts them into the ``instrument_daily_bar`` table.
"""

import logging
from datetime import date, timedelta

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.cache import cache_invalidate_pattern
from app.data.pipelines.base import ETLPipeline
from app.data.providers.akshare_provider import AkshareProvider
from app.models.etf import InstrumentDailyBar, ETFInfo

logger = logging.getLogger(__name__)


class AShareETLPipeline(ETLPipeline):
    """ETL pipeline for China A-share ETF daily bars."""

    job_name = "a_share_daily_etl"

    def __init__(self, db: Session, target_date: date | None = None, prefer_sina: bool = False) -> None:
        provider = AkshareProvider(prefer_sina=prefer_sina)
        super().__init__(provider=provider, db=db)
        self.target_date = target_date
        self.prefer_sina = prefer_sina

    def extract(self) -> pd.DataFrame:
        """Fetch daily bars for active A-share ETFs.

        By default fetches yesterday's bars. If ``target_date`` is provided,
        fetches bars for that date instead (used for backfilling missed runs).
        """
        # 1. Query active A-share ETFs from DB
        etfs = (
            self.db.query(ETFInfo)
            .filter(ETFInfo.market == "A股")
            .filter(ETFInfo.instrument_type == "ETF")
            .filter(ETFInfo.status == "active")
            .all()
        )

        if not etfs:
            return pd.DataFrame()

        codes = [etf.code for etf in etfs]
        self._expected_codes = codes

        # 2. Determine target trade date
        target_date = self.target_date or (date.today() - timedelta(days=1))

        # 3. Fetch daily bars (fetch a small window to cover weekends/holidays)
        start_date = target_date - timedelta(days=7)
        end_date = target_date

        df = self.provider.fetch_daily_bars(codes, start_date, end_date)

        if df.empty:
            return df

        # 4. Keep only target date's data
        df = df[df["trade_date"] == target_date].copy()

        return df

    def load(self, data: pd.DataFrame) -> int:
        """Upsert daily bar records into ``instrument_daily_bar``.

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
            # Drop None/NaN values so they don't overwrite existing data on conflict,
            # but keep legitimate zeros (e.g. volume=0, change_pct=0).
            record = {
                k: v
                for k, v in record.items()
                if v is not None
                and not (isinstance(v, float) and pd.isna(v))
            }
            records.append(record)

        if not records:
            return 0

        stmt = (
            insert(InstrumentDailyBar)
            .values(records)
            .on_conflict_do_update(
                index_elements=["etf_code", "trade_date"],
                set_={
                    "open": insert(InstrumentDailyBar).excluded.open,
                    "high": insert(InstrumentDailyBar).excluded.high,
                    "low": insert(InstrumentDailyBar).excluded.low,
                    "close": insert(InstrumentDailyBar).excluded.close,
                    "volume": insert(InstrumentDailyBar).excluded.volume,
                    "amount": insert(InstrumentDailyBar).excluded.amount,
                    "pre_close": insert(InstrumentDailyBar).excluded.pre_close,
                    "change_pct": insert(InstrumentDailyBar).excluded.change_pct,
                    "turnover_rate": insert(InstrumentDailyBar).excluded.turnover_rate,
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
            logger.exception("Failed to invalidate caches after daily bar ETL")

        return len(records)
