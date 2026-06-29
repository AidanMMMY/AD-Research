"""US equity daily ETL pipeline.

Fetches daily OHLCV bars for active US instruments that already have
historical price data, and upserts them into the ``instrument_daily_bar`` table.

Production data source: Tiingo (free tier: 50 req/hour, 500 symbols/month).
FMP is no longer used because its `historical-price-full` endpoint returns
403 for free-tier keys registered after the legacy endpoint deprecation.
yfinance is kept only as a last-resort fallback because batch downloads are
heavily rate-limited from cloud server IPs.
"""

import logging
import os
from datetime import date, timedelta

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.cache import cache_invalidate_pattern
from app.data.pipelines.base import ETLPipeline
from app.data.providers.tiingo_provider import TiingoProvider
from app.models.etf import InstrumentDailyBar, ETFInfo

logger = logging.getLogger(__name__)


class USDailyPipeline(ETLPipeline):
    """ETL pipeline for US equity daily bars.

    Covers active instruments with market="US" that already have historical
    price data. Uses Tiingo as primary source with yfinance fallback.
    Instruments without any price data are skipped here and handled by
    USHistoricalBackfillPipeline to avoid burning Tiingo's 500 symbols/month
    limit on symbols that may not be available.

    Scheduled at 05:00 Beijing time (17:00 ET, post-market).
    """

    job_name = "us_daily_etl"

    def __init__(
        self,
        db: Session,
        target_date: date | None = None,
    ) -> None:
        provider = TiingoProvider()
        super().__init__(provider=provider, db=db)
        self.target_date = target_date

    def _try_yfinance_fallback(
        self, codes: list[str], start_date: date, end_date: date
    ) -> pd.DataFrame:
        """Try yfinance as a last-resort fallback.

        Returns empty DataFrame if fallback fails.
        """
        try:
            from app.data.providers.yfinance_provider import YFinanceProvider

            fallback = YFinanceProvider()
            df = fallback.fetch_daily_bars(codes, start_date, end_date)
            if not df.empty:
                logger.info(
                    "USDailyPipeline: yfinance fallback returned %d rows", len(df)
                )
            return df
        except Exception as exc:
            logger.warning("USDailyPipeline: yfinance fallback failed: %s", exc)
            return pd.DataFrame()

    def _codes_with_price_data(self) -> set[str]:
        """Return set of US codes that already have at least one daily bar."""
        rows = (
            self.db.query(InstrumentDailyBar.etf_code)
            .distinct()
            .filter(InstrumentDailyBar.etf_code.like("%.US"))
            .all()
        )
        return {code for (code,) in rows}

    def extract(self) -> pd.DataFrame:
        """Fetch daily bars for active US instruments with existing data."""
        instruments = (
            self.db.query(ETFInfo)
            .filter(ETFInfo.market == "US")
            .filter(ETFInfo.status == "active")
            .all()
        )

        codes = [inst.code for inst in instruments]
        codes_with_data = self._codes_with_price_data()

        # Only update instruments that already have price history. New symbols
        # are backfilled by USHistoricalBackfillPipeline.
        codes = [c for c in codes if c in codes_with_data]

        if not codes:
            logger.info("USDailyPipeline: No US instruments with price data found")
            return pd.DataFrame()

        # Respect Tiingo free tier: 50 req/hour. Cap at 30 symbols per run.
        codes = codes[:30]
        self._expected_codes = codes
        logger.info("USDailyPipeline: Fetching %d US instruments", len(codes))

        target_date = self.target_date or (date.today() - timedelta(days=1))
        start_date = target_date - timedelta(days=7)
        end_date = target_date

        df = self.provider.fetch_daily_bars(codes, start_date, end_date)

        if df.empty:
            logger.warning(
                "USDailyPipeline: Primary (Tiingo) returned empty, trying yfinance fallback"
            )
            df = self._try_yfinance_fallback(codes, start_date, end_date)

        if df.empty:
            return df

        df = df[df["trade_date"] == target_date].copy()
        logger.info(
            "USDailyPipeline: Extracted %d rows for target date %s",
            len(df),
            target_date,
        )

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
            record = {k: v for k, v in record.items() if v is not None}
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
            logger.exception("Failed to invalidate caches after US daily bar ETL")

        return len(records)
