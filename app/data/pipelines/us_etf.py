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
from app.core.redis_client import get_redis_client
from app.data.pipelines.base import ETLPipeline
from app.data.providers.tiingo_provider import TiingoProvider
from app.data.providers.yfinance_provider import YFinanceProvider
from app.models.etf import InstrumentDailyBar, ETFInfo

logger = logging.getLogger(__name__)

# Tiingo free-tier daily limit for US daily bars.
_TIINGO_DAILY_LIMIT = 50

# Redis key for rotating which symbols are fetched via Tiingo each run.
_TIINGO_OFFSET_KEY = "us_daily:tiingo_offset"


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
        """Fetch daily bars for all active US instruments with existing data.

        Uses a rotating Tiingo batch (up to _TIINGO_DAILY_LIMIT symbols per
        run) and yfinance for the rest.  This spreads Tiingo's free-tier
        quota across all symbols while keeping daily coverage complete via
        yfinance fallback.
        """
        instruments = (
            self.db.query(ETFInfo)
            .filter(ETFInfo.market == "US")
            .filter(ETFInfo.status == "active")
            .order_by(ETFInfo.code.asc())
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

        self._expected_codes = codes

        target_date = self.target_date or (date.today() - timedelta(days=1))
        start_date = target_date - timedelta(days=7)
        end_date = target_date

        # Rotate the Tiingo batch so quota is spread across all symbols.
        offset = self._get_tiingo_offset()
        if offset >= len(codes):
            offset = 0
        tiingo_codes = codes[offset : offset + _TIINGO_DAILY_LIMIT]
        new_offset = (offset + len(tiingo_codes)) % len(codes)
        self._set_tiingo_offset(new_offset)
        logger.info(
            "USDailyPipeline: Tiingo batch %d symbols, offset %d -> %d",
            len(tiingo_codes), offset, new_offset,
        )

        frames: list[pd.DataFrame] = []

        # Primary: Tiingo for the rotating batch.
        if tiingo_codes:
            df_tiingo = self.provider.fetch_daily_bars(
                tiingo_codes, start_date, end_date
            )
            if not df_tiingo.empty:
                df_tiingo = df_tiingo[df_tiingo["trade_date"] == target_date].copy()
                if not df_tiingo.empty:
                    frames.append(df_tiingo)
                    logger.info(
                        "USDailyPipeline: Tiingo returned %d rows for target date %s",
                        len(df_tiingo), target_date,
                    )
            else:
                logger.warning(
                    "USDailyPipeline: Tiingo returned empty for batch, will rely on yfinance"
                )

        tiingo_fetched = set()
        if frames:
            tiingo_fetched = set(frames[0]["etf_code"].unique())

        # Fallback / remainder: yfinance for all symbols Tiingo did not cover.
        yf_codes = [c for c in codes if c not in tiingo_fetched]
        if yf_codes:
            logger.info(
                "USDailyPipeline: Fetching %d symbols via yfinance", len(yf_codes)
            )
            yf_provider = YFinanceProvider()
            df_yf = yf_provider.fetch_daily_bars(yf_codes, start_date, end_date)
            if not df_yf.empty:
                df_yf = df_yf[df_yf["trade_date"] == target_date].copy()
                if not df_yf.empty:
                    frames.append(df_yf)
                    logger.info(
                        "USDailyPipeline: yfinance returned %d rows for target date %s",
                        len(df_yf), target_date,
                    )
            else:
                logger.warning("USDailyPipeline: yfinance also returned empty")

        if not frames:
            logger.warning(
                "USDailyPipeline: No data returned for any symbol on %s", target_date
            )
            return pd.DataFrame()

        df = pd.concat(frames, ignore_index=True)
        logger.info(
            "USDailyPipeline: Extracted %d rows for target date %s",
            len(df), target_date,
        )
        return df

    def _get_tiingo_offset(self) -> int:
        """Return persisted Tiingo rotation offset, defaulting to 0."""
        try:
            redis_client = get_redis_client()
            value = redis_client.get(_TIINGO_OFFSET_KEY)
            return int(value) if value else 0
        except Exception as exc:
            logger.warning("Failed to read Tiingo offset from Redis: %s", exc)
            return 0

    def _set_tiingo_offset(self, offset: int) -> None:
        """Persist Tiingo rotation offset to Redis."""
        try:
            redis_client = get_redis_client()
            redis_client.set(_TIINGO_OFFSET_KEY, str(offset))
        except Exception as exc:
            logger.warning("Failed to write Tiingo offset to Redis: %s", exc)


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
                "adj_factor": row.get("adj_factor"),
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
                    "adj_factor": insert(InstrumentDailyBar).excluded.adj_factor,
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
