"""A-Share Individual Stock Daily ETL Pipeline.

Fetches daily OHLCV bars for all active China A-share individual stocks
and upserts them into the ``instrument_daily_bar`` table.

Uses TushareProvider's daily() endpoint as the data source.

Scheduled at 16:00 daily (after A-share market close at 15:00 CST).
"""

import logging
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import case, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.cache import cache_invalidate_pattern
from app.data.pipelines.base import ETLPipeline
from app.data.providers.tushare_provider import TushareProvider
from app.models.etf import AdjFactorHistory, ETFInfo, InstrumentDailyBar

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

        Uses the market-wide bulk endpoint (1 API call for all ~5000 stocks)
        when targeting a single date — the scheduler always targets yesterday.

        Falls back to per-stock fetching for date-range requests (legacy).
        """

        # 1. Query active A-share individual stocks from DB (for FK filtering)
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

        # 3. Fetch daily bars — use bulk endpoint for single-date fetches
        #    (1 API call for ~5000 stocks vs 5000 per-stock calls)
        df = self.provider.fetch_daily_all_market(trade_date=target_date)

        if df.empty:
            logger.info(
                "AStockDailyPipeline: No bars returned for %s (market closed?)",
                target_date,
            )
            return df

        # 4. Keep only our registered A-share stocks (filter out B-shares, etc.)
        known_codes = set(codes)
        before = len(df)
        df = df[df["etf_code"].isin(known_codes)].copy()
        logger.info(
            "AStockDailyPipeline: Bulk fetch %d rows → %d after filtering for %s",
            before, len(df), target_date,
        )

        return df

    def load(self, data: pd.DataFrame) -> int:
        """Upsert daily bar records into ``instrument_daily_bar``.

        Uses PostgreSQL ON CONFLICT DO UPDATE for idempotent writes.
        The unique key is (etf_code, trade_date).
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

        # Keep every row's key set identical (fill None instead of dropping).
        # Dropping None per row produces heterogeneous multi-row VALUES, which
        # makes SQLAlchemy render the missing column as a per-row bound
        # parameter and breaks ON CONFLICT DO UPDATE at compile time
        # (same production failure as a_share_daily_etl on 2026-07-16).
        records = []
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

        # Columns that are all NULL are omitted from the DO UPDATE SET so we
        # do not overwrite existing values with NULL.
        cols_with_data = [
            col
            for col in present_cols
            if col not in ("etf_code", "trade_date")
            and any(record.get(col) is not None for record in records)
        ]

        stmt = insert(InstrumentDailyBar).values(records)
        set_clause = {}
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

        # Also persist the target-date adj_factor into the authoritative
        # AdjFactorHistory table (full history is backfilled weekly).
        self._load_adj_factor_history(data)

        # Invalidate caches that depend on daily bar data
        try:
            cache_invalidate_pattern("indicator:*")
            cache_invalidate_pattern("screen:*")
            cache_invalidate_pattern("etf:list:*")
        except Exception:
            logger.exception("Failed to invalidate caches after A-stock daily ETL")

        return len(records)

    def _load_adj_factor_history(self, data: pd.DataFrame) -> int:
        """Upsert target-date adj_factor rows into ``adj_factor_history``."""
        if data.empty or "adj_factor" not in data.columns:
            return 0

        records = []
        for _, row in data.iterrows():
            af = row.get("adj_factor")
            if af is None or pd.isna(af):
                continue
            records.append(
                {
                    "etf_code": row.get("etf_code"),
                    "trade_date": row.get("trade_date"),
                    "adj_factor": float(af),
                    "source": "tushare",
                }
            )

        if not records:
            return 0

        stmt = (
            insert(AdjFactorHistory)
            .values(records)
            .on_conflict_do_update(
                index_elements=["etf_code", "trade_date"],
                set_={
                    "adj_factor": insert(AdjFactorHistory).excluded.adj_factor,
                    "source": insert(AdjFactorHistory).excluded.source,
                    "updated_at": func.now(),
                },
            )
        )
        self.db.execute(stmt)
        self.db.commit()
        logger.info(
            "AStockDailyPipeline: upserted %d rows into adj_factor_history",
            len(records),
        )
        return len(records)
