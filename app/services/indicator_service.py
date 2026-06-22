"""Technical indicator business logic service.

Provides queries for latest, historical, and batch technical indicators.
"""

from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.cache import cache_get, cache_set
from app.models.etf import ETFIndicator
from app.schemas.indicators import IndicatorBatchResponse, IndicatorResponse


class IndicatorService:
    """Service for technical indicator queries."""

    def __init__(self, db: Session):
        self.db = db

    def get_latest(self, code: str) -> IndicatorResponse | None:
        """Get the latest technical indicators for an ETF.

        Args:
            code: ETF code.

        Returns:
            IndicatorResponse or None if no data.
        """
        cache_key = f"indicator:latest:{code}"
        cached = cache_get(cache_key)
        if cached is not None:
            return IndicatorResponse(**cached) if cached else None

        indicator = (
            self.db.query(ETFIndicator)
            .filter(ETFIndicator.etf_code == code)
            .order_by(ETFIndicator.trade_date.desc())
            .first()
        )
        response = self._to_response(indicator) if indicator else None
        cache_set(cache_key, response.model_dump() if response else None, ttl=300)
        return response

    def get_history(
        self,
        code: str,
        start: date | None = None,
        end: date | None = None,
    ) -> list[IndicatorResponse]:
        """Get historical technical indicators for an ETF.

        Args:
            code: ETF code.
            start: Start date (inclusive).
            end: End date (inclusive).

        Returns:
            List of IndicatorResponse.
        """
        cache_key = f"indicator:history:{code}:{start}:{end}"
        cached = cache_get(cache_key)
        if cached is not None:
            return [IndicatorResponse(**item) for item in cached]

        query = self.db.query(ETFIndicator).filter(
            ETFIndicator.etf_code == code
        )

        if start:
            query = query.filter(ETFIndicator.trade_date >= start)
        if end:
            query = query.filter(ETFIndicator.trade_date <= end)

        indicators = query.order_by(ETFIndicator.trade_date.asc()).all()
        response = [self._to_response(ind) for ind in indicators]
        cache_set(cache_key, [item.model_dump() for item in response], ttl=300)
        return response

    def get_batch(
        self, codes: list[str], fields: list[str] | None = None
    ) -> IndicatorBatchResponse:
        """Get the latest indicators for a batch of ETF codes.

        Args:
            codes: List of ETF codes.
            fields: Optional list of field names to include. If None,
                all fields are returned.

        Returns:
            IndicatorBatchResponse.
        """
        cache_key = f"indicator:batch:{','.join(sorted(codes))}:{','.join(sorted(fields)) if fields else 'all'}"
        cached = cache_get(cache_key)
        if cached is not None:
            return IndicatorBatchResponse(**cached)

        if not codes:
            return IndicatorBatchResponse(items=[], count=0)

        # Subquery: latest trade_date per ETF
        latest_dates = (
            self.db.query(
                ETFIndicator.etf_code,
                func.max(ETFIndicator.trade_date).label("latest_date"),
            )
            .filter(ETFIndicator.etf_code.in_(codes))
            .group_by(ETFIndicator.etf_code)
            .subquery()
        )

        indicators = (
            self.db.query(ETFIndicator)
            .join(
                latest_dates,
                (ETFIndicator.etf_code == latest_dates.c.etf_code)
                & (ETFIndicator.trade_date == latest_dates.c.latest_date),
            )
            .all()
        )

        items = [self._to_response(ind) for ind in indicators]

        # If fields filter is specified, trim the response
        if fields:
            items = [
                IndicatorResponse(
                    **{
                        k: getattr(item, k)
                        for k in fields + ["etf_code", "trade_date"]
                        if hasattr(item, k)
                    }
                )
                for item in items
            ]

        response = IndicatorBatchResponse(items=items, count=len(items))
        cache_set(cache_key, response.model_dump(), ttl=300)
        return response

    @staticmethod
    def _to_response(indicator: ETFIndicator) -> IndicatorResponse:
        """Convert an ETFIndicator ORM object to IndicatorResponse."""
        return IndicatorResponse(
            etf_code=indicator.etf_code,
            trade_date=indicator.trade_date,
            ma5=float(indicator.ma5) if indicator.ma5 is not None else None,
            ma10=float(indicator.ma10)
            if indicator.ma10 is not None
            else None,
            ma20=float(indicator.ma20)
            if indicator.ma20 is not None
            else None,
            ma60=float(indicator.ma60)
            if indicator.ma60 is not None
            else None,
            rsi14=float(indicator.rsi14)
            if indicator.rsi14 is not None
            else None,
            macd_dif=float(indicator.macd_dif)
            if indicator.macd_dif is not None
            else None,
            macd_dea=float(indicator.macd_dea)
            if indicator.macd_dea is not None
            else None,
            macd_hist=float(indicator.macd_hist)
            if indicator.macd_hist is not None
            else None,
            volatility_20d=float(indicator.volatility_20d)
            if indicator.volatility_20d is not None
            else None,
            volatility_60d=float(indicator.volatility_60d)
            if indicator.volatility_60d is not None
            else None,
            max_drawdown_1y=float(indicator.max_drawdown_1y)
            if indicator.max_drawdown_1y is not None
            else None,
            sharpe_1y=float(indicator.sharpe_1y)
            if indicator.sharpe_1y is not None
            else None,
            return_1w=float(indicator.return_1w)
            if indicator.return_1w is not None
            else None,
            return_1m=float(indicator.return_1m)
            if indicator.return_1m is not None
            else None,
            return_3m=float(indicator.return_3m)
            if indicator.return_3m is not None
            else None,
            return_6m=float(indicator.return_6m)
            if indicator.return_6m is not None
            else None,
            return_1y=float(indicator.return_1y)
            if indicator.return_1y is not None
            else None,
            atr14=float(indicator.atr14)
            if indicator.atr14 is not None
            else None,
            bb_upper=float(indicator.bb_upper)
            if indicator.bb_upper is not None
            else None,
            bb_lower=float(indicator.bb_lower)
            if indicator.bb_lower is not None
            else None,
        )
