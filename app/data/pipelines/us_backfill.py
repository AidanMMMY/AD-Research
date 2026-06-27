"""US equity historical backfill pipeline.

Slowly backfills daily OHLCV bars for US instruments using free-tier
providers. Designed to run repeatedly from the scheduler, processing a
small batch each time to stay within API rate limits.

Rotation strategy:
  - All active US instruments are sorted by code.
  - Each run consumes a fixed batch starting from a persisted offset.
  - The offset is stored in Redis and wraps around when the list ends.
  - Instruments without any price data are always processed first.

Rate limits (free tier):
  - FMP: 250 requests/day. We use it as primary.
  - Tiingo: 50 requests/hour, 500 symbols/month. Used as fallback only.
"""

import logging
import os
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.cache import cache_invalidate_pattern
from app.core.redis_client import get_redis_client
from app.data.pipelines.base import ETLPipeline
from app.data.providers.fmp_provider import FMPProvider
from app.models.etf import ETFDailyBar, ETFInfo

logger = logging.getLogger(__name__)

# Number of instruments to process per run. FMP free tier allows 250
# requests/day; processing 30 instruments per run every 6 hours keeps us
# safely below the limit while making steady progress.
_BATCH_SIZE = 30

# How many days of history to request per instrument.
_HISTORY_DAYS = 90

# Redis key for the rotation offset.
_OFFSET_KEY = "us_backfill:offset"


class USHistoricalBackfillPipeline(ETLPipeline):
    """Slow backfill pipeline for US equity daily bars."""

    job_name = "us_historical_backfill"

    def __init__(self, db: Session) -> None:
        provider = FMPProvider()
        super().__init__(provider=provider, db=db)
        self.redis = get_redis_client()

    def _get_active_us_codes(self) -> list[str]:
        """Return sorted list of active US instrument codes."""
        instruments = (
            self.db.query(ETFInfo.code)
            .filter(ETFInfo.market == "US")
            .filter(ETFInfo.status == "active")
            .order_by(ETFInfo.code.asc())
            .all()
        )
        return [code for (code,) in instruments]

    def _get_codes_with_price_data(self) -> set[str]:
        """Return set of US codes that already have at least one daily bar."""
        rows = (
            self.db.query(ETFDailyBar.etf_code)
            .distinct()
            .filter(ETFDailyBar.etf_code.like("%.US"))
            .all()
        )
        return {code for (code,) in rows}

    def _get_offset(self) -> int:
        """Return persisted rotation offset, defaulting to 0."""
        try:
            value = self.redis.get(_OFFSET_KEY)
            return int(value) if value else 0
        except Exception as exc:
            logger.warning("Failed to read backfill offset from Redis: %s", exc)
            return 0

    def _set_offset(self, offset: int) -> None:
        """Persist rotation offset to Redis."""
        try:
            self.redis.set(_OFFSET_KEY, str(offset))
        except Exception as exc:
            logger.warning("Failed to write backfill offset to Redis: %s", exc)

    def _select_batch(self, codes: list[str], codes_with_data: set[str]) -> list[str]:
        """Select the next batch of codes to backfill.

        Prioritizes instruments without any price data. Once all instruments
        have at least some data, rotates through the full list in chunks.
        """
        if not codes:
            return []

        missing_codes = [c for c in codes if c not in codes_with_data]

        if missing_codes:
            # Always backfill missing-data instruments first, in code order.
            batch = missing_codes[:_BATCH_SIZE]
            logger.info(
                "USBackfill: %d instruments lack price data; processing first %d",
                len(missing_codes),
                len(batch),
            )
            return batch

        # All instruments have some data; rotate through the list.
        offset = self._get_offset()
        if offset >= len(codes):
            offset = 0

        rotated = codes[offset:] + codes[:offset]
        batch = rotated[:_BATCH_SIZE]
        new_offset = (offset + len(batch)) % len(codes)
        self._set_offset(new_offset)
        logger.info(
            "USBackfill: rotating through %d instruments, offset %d -> %d, batch %d",
            len(codes),
            offset,
            new_offset,
            len(batch),
        )
        return batch

    def _try_tiingo_fallback(
        self, codes: list[str], start_date: date, end_date: date
    ) -> pd.DataFrame:
        """Try Tiingo as a fallback if FMP fails."""
        tiingo_key = os.getenv("TIINGO_API_KEY", "")
        if not tiingo_key:
            return pd.DataFrame()

        try:
            from app.data.providers.tiingo_provider import TiingoProvider

            fallback = TiingoProvider()
            df = fallback.fetch_daily_bars(codes, start_date, end_date)
            if not df.empty:
                logger.info(
                    "USBackfill: Tiingo fallback returned %d rows", len(df)
                )
            return df
        except Exception as exc:
            logger.warning("USBackfill: Tiingo fallback failed: %s", exc)
            return pd.DataFrame()

    def extract(self) -> pd.DataFrame:
        """Fetch historical daily bars for the current batch."""
        codes = self._get_active_us_codes()
        codes_with_data = self._get_codes_with_price_data()
        batch = self._select_batch(codes, codes_with_data)

        if not batch:
            logger.info("USBackfill: No active US instruments to backfill")
            return pd.DataFrame()

        self._expected_codes = batch
        logger.info(
            "USBackfill: Fetching %d US instruments for historical backfill",
            len(batch),
        )

        end_date = date.today()
        start_date = end_date - timedelta(days=_HISTORY_DAYS)

        df = self.provider.fetch_daily_bars(batch, start_date, end_date)

        if df.empty:
            logger.warning(
                "USBackfill: Primary (FMP) returned empty, trying Tiingo fallback"
            )
            df = self._try_tiingo_fallback(batch, start_date, end_date)

        if df.empty:
            logger.warning("USBackfill: No data returned for batch")
            return df

        logger.info(
            "USBackfill: Extracted %d rows for %d instruments",
            len(df),
            df["etf_code"].nunique(),
        )
        return df

    def load(self, data: pd.DataFrame) -> int:
        """Upsert daily bar records into ``etf_daily_bar``."""
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
            logger.exception("Failed to invalidate caches after US backfill")

        return len(records)
