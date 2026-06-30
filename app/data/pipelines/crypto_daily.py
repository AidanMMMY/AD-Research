"""Crypto daily ETL pipeline.

Fetches daily OHLCV bars for active cryptocurrency instruments from
Binance and upserts them into the ``instrument_daily_bar`` table.

Scheduled at 08:05 CST (00:05 UTC) daily, immediately after the
UTC-midnight daily candle closes. The container runs in Asia/Shanghai
timezone so the CronTrigger value is 08:05 local time.
"""

import logging
from datetime import date, timedelta

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.cache import cache_invalidate_pattern
from app.data.pipelines.base import ETLPipeline
from app.data.providers.binance_provider import BinanceProvider, _DEFAULT_CRYPTO
from app.models.etf import InstrumentDailyBar, ETFInfo

logger = logging.getLogger(__name__)

# Keep the pipeline seed list identical to the provider's curated list so the
# two stay in sync automatically.
_SEED_INSTRUMENTS = _DEFAULT_CRYPTO


class CryptoDailyPipeline(ETLPipeline):
    """ETL pipeline for cryptocurrency daily bars.

    Sources data from Binance and loads it into ``instrument_daily_bar``.
    Reuses the polymorphic ``etf_info`` table (market="CRYPTO") so
    that all downstream indicator / scoring / signal / backtest engines
    work for crypto without schema changes.
    """

    job_name = "crypto_daily_etl"

    def __init__(
        self,
        db: Session,
        target_date: date | None = None,
        seed_instruments: bool = True,
    ) -> None:
        provider = BinanceProvider()
        super().__init__(provider=provider, db=db)
        self.target_date = target_date
        self._seed_on_first_run = seed_instruments
        self._expected_codes: list[str] | None = None

    # ------------------------------------------------------------------
    # Extract
    # ------------------------------------------------------------------

    def _ensure_instruments(self) -> list[ETFInfo]:
        """Ensure crypto instruments exist in ``etf_info``.

        On first run inserts the curated list of instruments so that
        downstream queries (filtered by market="CRYPTO") return them.
        Subsequent runs are a no-op because of ON CONFLICT DO NOTHING.
        """
        records: list[dict] = []
        for code, name, category in _SEED_INSTRUMENTS:
            records.append(
                {
                    "code": code,
                    "name": name,
                    "market": "CRYPTO",
                    "exchange": "BINANCE",
                    "category": category,
                    "currency": "USDT",
                    "instrument_type": "CRYPTO",
                    "status": "active",
                }
            )

        stmt = (
            insert(ETFInfo)
            .values(records)
            .on_conflict_do_update(
                index_elements=["code"],
                set_={
                    "name": insert(ETFInfo).excluded.name,
                    "category": insert(ETFInfo).excluded.category,
                    "instrument_type": insert(ETFInfo).excluded.instrument_type,
                },
            )
        )
        self.db.execute(stmt)
        self.db.commit()
        logger.info(
            "CryptoDailyPipeline: Ensured %d crypto instruments in etf_info",
            len(records),
        )

    def extract(self) -> pd.DataFrame:
        """Fetch daily bars for active crypto instruments."""
        if self._seed_on_first_run:
            self._ensure_instruments()

        instruments = (
            self.db.query(ETFInfo)
            .filter(ETFInfo.market == "CRYPTO")
            .filter(ETFInfo.status == "active")
            .all()
        )

        if not instruments:
            logger.info(
                "CryptoDailyPipeline: No active crypto instruments found"
            )
            return pd.DataFrame()

        codes = [inst.code for inst in instruments]
        self._expected_codes = codes
        logger.info(
            "CryptoDailyPipeline: Fetching %d crypto instruments", len(codes)
        )

        # Crypto markets are 24/7.  The target date is "yesterday" in UTC
        # because the daily candle closes at 00:00 UTC.
        target_date = self.target_date or (date.today() - timedelta(days=1))
        # Fetch a 7-day window to give the normaliser/validator context
        start_date = target_date - timedelta(days=7)
        end_date = target_date

        df = self.provider.fetch_daily_bars(codes, start_date, end_date)

        if df.empty:
            logger.warning(
                "CryptoDailyPipeline: Binance returned empty DataFrame"
            )
            return df

        # Keep only the target date
        df = df[df["trade_date"] == target_date].copy()
        logger.info(
            "CryptoDailyPipeline: Extracted %d rows for target date %s",
            len(df),
            target_date,
        )
        return df

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(self, data: pd.DataFrame) -> int:
        """Upsert daily bar records into ``instrument_daily_bar``.

        Uses PostgreSQL ON CONFLICT DO UPDATE for idempotent writes.
        The unique key is (etf_code, trade_date).
        """
        if data.empty:
            return 0

        records: list[dict] = []
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
            # but keep legitimate zeros.
            record = {k: v for k, v in record.items() if pd.notna(v)}
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

        # Invalidate downstream caches
        try:
            cache_invalidate_pattern("indicator:*")
            cache_invalidate_pattern("screen:*")
            cache_invalidate_pattern("etf:list:*")
        except Exception:
            logger.exception(
                "Failed to invalidate caches after crypto daily bar ETL"
            )

        return len(records)
