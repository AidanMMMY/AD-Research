"""Market data business logic service.

Provides queries for historical OHLCV bars and market snapshots.
"""

import math
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.etf import ETFDailyBar, ETFInfo
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
    ) -> MarketDataHistoryResponse:
        """Get historical OHLCV bars for an ETF.

        Args:
            code: ETF code.
            start: Start date (inclusive).
            end: End date (inclusive).
            limit: Maximum number of most recent bars to return.

        Returns:
            MarketDataHistoryResponse with bars and ETF info.
        """
        query = self.db.query(ETFDailyBar).filter(
            ETFDailyBar.etf_code == code
        )

        if start:
            query = query.filter(ETFDailyBar.trade_date >= start)
        if end:
            query = query.filter(ETFDailyBar.trade_date <= end)

        # Apply limit: get most recent N bars, then reverse to chronological order
        if limit and limit > 0:
            bars_desc = query.order_by(ETFDailyBar.trade_date.desc()).limit(limit).all()
            bars = list(reversed(bars_desc))
        else:
            bars = query.order_by(ETFDailyBar.trade_date.asc()).all()

        etf = (
            self.db.query(ETFInfo.name)
            .filter(ETFInfo.code == code)
            .scalar()
        )

        items = [
            DailyBarResponse(
                trade_date=bar.trade_date,
                open=_safe_float(bar.open),
                high=_safe_float(bar.high),
                low=_safe_float(bar.low),
                close=_safe_float(bar.close),
                volume=int(bar.volume) if bar.volume is not None else None,
                amount=_safe_float(bar.amount),
                change_pct=_safe_float(bar.change_pct),
                turnover_rate=_safe_float(bar.turnover_rate),
            )
            for bar in bars
        ]

        return MarketDataHistoryResponse(
            etf_code=code,
            etf_name=etf,
            items=items,
        )

    def get_snapshot(self, codes: list[str]) -> MarketSnapshotResponse:
        """Get the latest market snapshot for a list of ETF codes.

        For each code, returns the most recent daily bar.

        Args:
            codes: List of ETF codes.

        Returns:
            MarketSnapshotResponse with snapshot items.
        """
        if not codes:
            return MarketSnapshotResponse(items=[], count=0)

        # Subquery: latest trade_date per ETF
        latest_dates = (
            self.db.query(
                ETFDailyBar.etf_code,
                func.max(ETFDailyBar.trade_date).label("latest_date"),
            )
            .filter(ETFDailyBar.etf_code.in_(codes))
            .group_by(ETFDailyBar.etf_code)
            .subquery()
        )

        results = (
            self.db.query(
                ETFDailyBar.etf_code,
                ETFInfo.name,
                ETFDailyBar.close,
                ETFDailyBar.change_pct,
                ETFDailyBar.volume,
                ETFDailyBar.amount,
            )
            .join(
                latest_dates,
                (ETFDailyBar.etf_code == latest_dates.c.etf_code)
                & (ETFDailyBar.trade_date == latest_dates.c.latest_date),
            )
            .outerjoin(ETFInfo, ETFDailyBar.etf_code == ETFInfo.code)
            .all()
        )

        items = [
            SnapshotItem(
                etf_code=r.etf_code,
                etf_name=r.name,
                close=_safe_float(r.close),
                change_pct=_safe_float(r.change_pct),
                volume=int(r.volume) if r.volume is not None else None,
                amount=_safe_float(r.amount),
            )
            for r in results
        ]

        return MarketSnapshotResponse(items=items, count=len(items))
