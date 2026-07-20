"""A-share ETF daily ETL pipeline.

Fetches daily OHLCV bars for all active China A-share ETFs and
upserts them into the ``instrument_daily_bar`` table.
"""

import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import case
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

        All records are normalized to the same set of keys so SQLAlchemy can
        compile a bulk INSERT.  For idempotent reruns, a ``CASE`` expression
        keeps the existing row value when the incoming value is NULL, which
        avoids wiping already-populated columns when a fallback source
        (e.g. Sina) is missing a field like ``turnover_rate``.
        """
        if data.empty:
            return 0

        all_cols = [
            "etf_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "pre_close",
            "change_pct",
            "turnover_rate",
            "adj_factor",
        ]
        present_cols = [c for c in all_cols if c in data.columns]

        records: list[dict] = []
        for _, row in data.iterrows():
            record = {}
            for col in present_cols:
                v = row.get(col)
                if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
                    record[col] = None
                else:
                    record[col] = v
            records.append(record)

        if not records:
            return 0

        # Determine which columns actually carry data.  Columns that are all
        # NULL are omitted from the DO UPDATE SET so we do not overwrite
        # existing values with NULL.
        cols_with_data = [
            col
            for col in present_cols
            if col not in ("etf_code", "trade_date")
            and any(record.get(col) is not None for record in records)
        ]

        # All-NULL columns are also dropped from the INSERT payload
        # (uniformly across rows, keeping the key set homogeneous): an
        # explicit NULL would violate NOT NULL columns such as adj_factor,
        # while omitting the column lets its default (1.0) apply on new
        # rows. The real factor is supplied by the weekly Tushare backfill.
        all_null_cols = [
            col
            for col in present_cols
            if col not in ("etf_code", "trade_date") and col not in cols_with_data
        ]
        if all_null_cols:
            records = [
                {k: v for k, v in record.items() if k not in all_null_cols}
                for record in records
            ]

        stmt = insert(InstrumentDailyBar).values(records)
        set_clause: dict[str, Any] = {}
        for col in cols_with_data:
            excluded_col = getattr(stmt.excluded, col)
            set_clause[col] = case(
                (excluded_col.is_not(None), excluded_col),
                else_=getattr(InstrumentDailyBar, col),
            )

        stmt = stmt.on_conflict_do_update(
            index_elements=["etf_code", "trade_date"],
            set_=set_clause,
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
