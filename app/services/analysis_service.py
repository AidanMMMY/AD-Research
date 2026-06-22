"""Analysis tools business logic service.

Provides correlation analysis, ranking, and screening capabilities.
"""

from typing import Literal

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.etf import ETFIndicator, ETFInfo


class AnalysisService:
    """Service for ETF analysis tools."""

    def __init__(self, db: Session):
        self.db = db

    def correlation_matrix(
        self,
        codes: list[str],
        window: int = 60,
        method: Literal["pearson", "spearman"] = "pearson",
    ) -> dict:
        """Compute the return correlation matrix for a list of ETFs.

        Uses close prices from ETFDailyBar to compute daily
        returns, then calculates the correlation over the last `window`
        days.

        Args:
            codes: List of ETF codes.
            window: Number of recent trading days to use.
            method: Correlation method, "pearson" or "spearman".

        Returns:
            Dict with keys: codes, matrix, method.
        """
        if len(codes) < 2:
            return {
                "codes": codes,
                "matrix": [[1.0]] if codes else [],
                "method": method,
            }

        # Fetch close prices from daily bars for each code, ordered by date
        from app.models.etf import ETFDailyBar

        data = {}
        for code in codes:
            rows = (
                self.db.query(ETFDailyBar.trade_date, ETFDailyBar.close)
                .filter(ETFDailyBar.etf_code == code)
                .filter(ETFDailyBar.close.isnot(None))
                .order_by(ETFDailyBar.trade_date.asc())
                .limit(window * 2)
                .all()
            )
            if len(rows) >= 2:
                prices = np.array([float(r.close) for r in rows])
                returns = np.diff(prices) / prices[:-1]
                # Take the last `window` returns
                data[code] = returns[-window:]

        # Only keep codes with sufficient data
        valid_codes = [c for c in codes if c in data and len(data[c]) >= 2]
        if len(valid_codes) < 2:
            n = len(valid_codes)
            return {
                "codes": valid_codes,
                "matrix": (
                    np.eye(n).tolist() if n > 0 else []
                ),
                "method": method,
            }

        # Build aligned return matrix (pad shorter series with NaN)
        max_len = max(len(data[c]) for c in valid_codes)
        returns_matrix = np.full((len(valid_codes), max_len), np.nan)
        for i, code in enumerate(valid_codes):
            series = data[code]
            returns_matrix[i, -len(series):] = series

        # Compute correlation, ignoring NaNs pairwise
        if method == "spearman":
            # Rank-based correlation
            corr = np.full((len(valid_codes), len(valid_codes)), np.nan)
            for i in range(len(valid_codes)):
                for j in range(len(valid_codes)):
                    mask = ~np.isnan(returns_matrix[i]) & ~np.isnan(
                        returns_matrix[j]
                    )
                    if mask.sum() >= 2:
                        from scipy.stats import spearmanr

                        corr[i, j], _ = spearmanr(
                            returns_matrix[i][mask],
                            returns_matrix[j][mask],
                        )
        else:
            # Pearson correlation with pairwise complete observations
            corr = np.full((len(valid_codes), len(valid_codes)), np.nan)
            for i in range(len(valid_codes)):
                for j in range(len(valid_codes)):
                    mask = ~np.isnan(returns_matrix[i]) & ~np.isnan(
                        returns_matrix[j]
                    )
                    if mask.sum() >= 2:
                        corr[i, j] = np.corrcoef(
                            returns_matrix[i][mask],
                            returns_matrix[j][mask],
                        )[0, 1]

        # Fill diagonal with 1.0 and handle NaNs
        for i in range(len(valid_codes)):
            corr[i, i] = 1.0
        corr = np.nan_to_num(corr, nan=0.0)

        return {
            "codes": valid_codes,
            "matrix": corr.tolist(),
            "method": method,
        }

    def ranking(
        self,
        sort_by: str = "sharpe_1y",
        order: Literal["asc", "desc"] = "desc",
        limit: int = 20,
        market: str | None = None,
    ) -> list[dict]:
        """Rank ETFs by a specific indicator field.

        Takes the latest indicator for each ETF and sorts by the
        specified field.

        Args:
            sort_by: Field name to sort by.
            order: "asc" or "desc".
            limit: Maximum number of results.
            market: Optional market filter.

        Returns:
            List of dicts with ETF code, name, and indicator values.
        """
        # Subquery: latest trade_date per ETF
        latest_dates = (
            self.db.query(
                ETFIndicator.etf_code,
                func.max(ETFIndicator.trade_date).label("latest_date"),
            )
            .group_by(ETFIndicator.etf_code)
            .subquery()
        )

        query = self.db.query(
            ETFIndicator,
            ETFInfo.name.label("etf_name"),
        ).join(
            latest_dates,
            (ETFIndicator.etf_code == latest_dates.c.etf_code)
            & (ETFIndicator.trade_date == latest_dates.c.latest_date),
        ).outerjoin(
            ETFInfo, ETFIndicator.etf_code == ETFInfo.code
        )

        if market:
            query = query.filter(ETFInfo.market == market)

        # Dynamic sort
        sort_column = getattr(ETFIndicator, sort_by, None)
        if sort_column is not None:
            if order == "desc":
                query = query.order_by(sort_column.desc().nullslast())
            else:
                query = query.order_by(sort_column.asc().nullsfirst())

        results = query.limit(limit).all()

        return [
            {
                "etf_code": r.ETFIndicator.etf_code,
                "etf_name": r.etf_name,
                "trade_date": r.ETFIndicator.trade_date.isoformat(),
                "ma5": float(r.ETFIndicator.ma5)
                if r.ETFIndicator.ma5 is not None
                else None,
                "rsi14": float(r.ETFIndicator.rsi14)
                if r.ETFIndicator.rsi14 is not None
                else None,
                "sharpe_1y": float(r.ETFIndicator.sharpe_1y)
                if r.ETFIndicator.sharpe_1y is not None
                else None,
                "volatility_20d": float(r.ETFIndicator.volatility_20d)
                if r.ETFIndicator.volatility_20d is not None
                else None,
                "return_1y": float(r.ETFIndicator.return_1y)
                if r.ETFIndicator.return_1y is not None
                else None,
                "max_drawdown_1y": float(r.ETFIndicator.max_drawdown_1y)
                if r.ETFIndicator.max_drawdown_1y is not None
                else None,
            }
            for r in results
        ]

    def screen(
        self,
        market: str | None = None,
        category: str | None = None,
        rsi_min: float | None = None,
        rsi_max: float | None = None,
        sharpe_min: float | None = None,
        volatility_max: float | None = None,
    ) -> list[dict]:
        """Screen ETFs based on indicator criteria.

        Takes the latest indicator for each ETF and filters by the
        specified conditions.

        Args:
            market: Optional market filter.
            category: Optional category filter.
            rsi_min: Minimum RSI14 value.
            rsi_max: Maximum RSI14 value.
            sharpe_min: Minimum Sharpe ratio.
            volatility_max: Maximum 20-day volatility.

        Returns:
            List of dicts with ETF code, name, and indicator values.
        """
        # Subquery: latest trade_date per ETF
        latest_dates = (
            self.db.query(
                ETFIndicator.etf_code,
                func.max(ETFIndicator.trade_date).label("latest_date"),
            )
            .group_by(ETFIndicator.etf_code)
            .subquery()
        )

        query = self.db.query(
            ETFIndicator,
            ETFInfo.name.label("etf_name"),
            ETFInfo.market,
            ETFInfo.category,
        ).join(
            latest_dates,
            (ETFIndicator.etf_code == latest_dates.c.etf_code)
            & (ETFIndicator.trade_date == latest_dates.c.latest_date),
        ).outerjoin(
            ETFInfo, ETFIndicator.etf_code == ETFInfo.code
        )

        if market:
            query = query.filter(ETFInfo.market == market)
        if category:
            query = query.filter(ETFInfo.category == category)
        if rsi_min is not None:
            query = query.filter(ETFIndicator.rsi14 >= rsi_min)
        if rsi_max is not None:
            query = query.filter(ETFIndicator.rsi14 <= rsi_max)
        if sharpe_min is not None:
            query = query.filter(ETFIndicator.sharpe_1y >= sharpe_min)
        if volatility_max is not None:
            query = query.filter(
                ETFIndicator.volatility_20d <= volatility_max
            )

        results = query.all()

        return [
            {
                "etf_code": r.ETFIndicator.etf_code,
                "etf_name": r.etf_name,
                "market": r.market,
                "category": r.category,
                "trade_date": r.ETFIndicator.trade_date.isoformat(),
                "rsi14": float(r.ETFIndicator.rsi14)
                if r.ETFIndicator.rsi14 is not None
                else None,
                "sharpe_1y": float(r.ETFIndicator.sharpe_1y)
                if r.ETFIndicator.sharpe_1y is not None
                else None,
                "volatility_20d": float(r.ETFIndicator.volatility_20d)
                if r.ETFIndicator.volatility_20d is not None
                else None,
                "return_1y": float(r.ETFIndicator.return_1y)
                if r.ETFIndicator.return_1y is not None
                else None,
                "max_drawdown_1y": float(r.ETFIndicator.max_drawdown_1y)
                if r.ETFIndicator.max_drawdown_1y is not None
                else None,
            }
            for r in results
        ]
