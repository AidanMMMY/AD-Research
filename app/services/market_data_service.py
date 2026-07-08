"""Market data business logic service.

Provides queries for historical OHLCV bars and market snapshots.
"""

import math
from datetime import date

from sqlalchemy.orm import Session

from app.data.repositories import price_repository
from app.models.etf import ETFInfo
from app.schemas.market_data import (
    DailyBarResponse,
    MarketDataHistoryResponse,
    MarketSnapshotResponse,
    SnapshotItem,
)


def _safe_float(value) -> float | None:
    """Convert a value to float, returning None for NaN/Inf."""
    if value is None:
        return None
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


class MarketDataService:
    """Service for market data queries."""

    def __init__(self, db: Session):
        self.db = db

    def get_history(
        self,
        code: str,
        start: date | None = None,
        end: date | None = None,
        limit: int | None = None,
        adjusted: bool = False,
    ) -> MarketDataHistoryResponse:
        """Get historical OHLCV bars for an instrument.

        When ``adjusted=True`` the repository returns an ``adj_close`` column
        computed as ``close * adj_factor``. We forward that into the response
        along with the raw ``adj_factor`` so the frontend can re-derive
        open/high/low/close for the K-line view.
        """
        df = price_repository.get_bars(
            self.db, code, start, end, adjusted=adjusted, limit=limit
        )

        etf = (
            self.db.query(ETFInfo.name)
            .filter(ETFInfo.code == code)
            .scalar()
        )

        items = [
            DailyBarResponse(
                trade_date=row["trade_date"],
                open=_safe_float(row.get("open")),
                high=_safe_float(row.get("high")),
                low=_safe_float(row.get("low")),
                close=_safe_float(row.get("close")),
                volume=int(row["volume"]) if row.get("volume") is not None else None,
                amount=_safe_float(row.get("amount")),
                change_pct=_safe_float(row.get("change_pct")),
                turnover_rate=_safe_float(row.get("turnover_rate")),
                adj_factor=_safe_float(row.get("adj_factor")),
                adj_close=_safe_float(row.get("adj_close")) if adjusted else None,
            )
            for _, row in df.iterrows()
        ]

        return MarketDataHistoryResponse(
            etf_code=code,
            etf_name=etf,
            items=items,
        )

    def get_snapshot(self, codes: list[str]) -> MarketSnapshotResponse:
        """Get the latest market snapshot for a list of ETF codes."""
        if not codes:
            return MarketSnapshotResponse(items=[], count=0)

        latest = price_repository.get_latest_bars(self.db, codes)
        etf_names = {
            r.code: r.name
            for r in self.db.query(ETFInfo.code, ETFInfo.name)
            .filter(ETFInfo.code.in_(codes))
            .all()
        }

        items = [
            SnapshotItem(
                etf_code=code,
                etf_name=etf_names.get(code),
                close=_safe_float(bar.close),
                change_pct=_safe_float(bar.change_pct),
                volume=int(bar.volume) if bar.volume is not None else None,
                amount=_safe_float(bar.amount),
            )
            for code, bar in latest.items()
        ]

        return MarketSnapshotResponse(items=items, count=len(items))
