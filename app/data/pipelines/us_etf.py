"""US equity daily ETL pipeline.

Fetches daily OHLCV bars for all active US instruments (ETFs and stocks)
and upserts them into the ``etf_daily_bar`` table.

Uses a fallback chain: yfinance (primary) → Tiingo → Finnhub.
"""

import logging
import os
from datetime import date, timedelta

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.cache import cache_invalidate_pattern
from app.data.pipelines.base import ETLPipeline
from app.data.providers.fmp_provider import FMPProvider
from app.models.etf import ETFDailyBar, ETFInfo

logger = logging.getLogger(__name__)


class USDailyPipeline(ETLPipeline):
    """ETL pipeline for US equity daily bars.

    Covers all active instruments with market="US" (ETFs + individual stocks).
    Uses FMP as primary source (free tier: 250 req/day) with Tiingo fallback.
    yfinance is intentionally not used in production because batch downloads
    are heavily rate-limited from cloud server IPs.

    Target date: yesterday's date (US market closes 16:00 ET → next day
    Beijing time). Run at 05:00 Beijing time = 17:00 ET previous day.
    """

    job_name = "us_daily_etl"

    def __init__(
        self,
        db: Session,
        target_date: date | None = None,
    ) -> None:
        provider = FMPProvider()
        super().__init__(provider=provider, db=db)
        self.target_date = target_date

    def _try_fallback(self, codes: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        """Try Tiingo fallback if FMP fails.

        Returns empty DataFrame if fallback fails.
        """
        tiingo_key = os.getenv("TIINGO_API_KEY", "")
        if not tiingo_key:
            return pd.DataFrame()

        try:
            from app.data.providers.tiingo_provider import TiingoProvider

            fallback = TiingoProvider()
            df = fallback.fetch_daily_bars(codes, start_date, end_date)
            if not df.empty:
                logger.info("USDailyPipeline: Tiingo fallback returned %d rows", len(df))
            return df
        except Exception as exc:
            logger.warning("USDailyPipeline: Tiingo fallback failed: %s", exc)

        return pd.DataFrame()

    def extract(self) -> pd.DataFrame:
        """Fetch daily bars for all active US instruments.

        Queries instruments with market="US" and status="active",
        then fetches OHLCV bars via yfinance (batch) with fallback chain.
        """
        # 1. Query active US instruments from DB
        instruments = (
            self.db.query(ETFInfo)
            .filter(ETFInfo.market == "US")
            .filter(ETFInfo.status == "active")
            .all()
        )

        if not instruments:
            logger.info("USDailyPipeline: No active US instruments found")
            return pd.DataFrame()

        codes = [inst.code for inst in instruments]
        self._expected_codes = codes
        logger.info("USDailyPipeline: Fetching %d US instruments", len(codes))

        # 2. Determine target trade date
        target_date = self.target_date or (date.today() - timedelta(days=1))

        # 3. Fetch daily bars (7-day window to cover weekends/holidays)
        start_date = target_date - timedelta(days=7)
        end_date = target_date

        df = self.provider.fetch_daily_bars(codes, start_date, end_date)

        if df.empty:
            logger.warning(
                "USDailyPipeline: Primary (FMP) returned empty, trying Tiingo fallback"
            )
            df = self._try_fallback(codes, start_date, end_date)

        if df.empty:
            return df

        # 4. Keep only target date's data
        df = df[df["trade_date"] == target_date].copy()
        logger.info(
            "USDailyPipeline: Extracted %d rows for target date %s",
            len(df),
            target_date,
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
            logger.exception("Failed to invalidate caches after US daily bar ETL")

        return len(records)
