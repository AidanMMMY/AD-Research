"""Portfolio risk analysis service.

Computes common risk metrics from historical daily bars using adjusted close:
  - annualized volatility
  - maximum drawdown
  - Value-at-Risk (VaR) via historical simulation and parametric method
  - Expected Shortfall (ES / CVaR)
  - portfolio-level metrics (weighted combination of assets)
"""

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.data.repositories import price_repository


class RiskAnalysisService:
    """Service for computing portfolio and instrument risk metrics."""

    def __init__(self, db: Session):
        self.db = db

    def _load_returns(
        self,
        codes: list[str],
        window: int = 252,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        """Load daily returns for a list of codes over a lookback window."""
        end_date = end_date or date.today()
        start_date = end_date - timedelta(days=window * 2)

        frames: list[pd.DataFrame] = []
        for code in codes:
            df = price_repository.get_bars(
                self.db, code, start_date, end_date, adjusted=True
            )
            if df.empty or len(df) < 2:
                continue
            df = df.sort_values("trade_date").reset_index(drop=True)
            df["return"] = df["adj_close"].pct_change()
            frames.append(df[["trade_date", "return"]].rename(columns={"return": code}))

        if not frames:
            return pd.DataFrame()

        merged = frames[0]
        for f in frames[1:]:
            merged = pd.merge(merged, f, on="trade_date", how="outer")
        merged = merged.sort_values("trade_date").dropna()
        return merged.set_index("trade_date").tail(window)

    @staticmethod
    def _portfolio_returns(returns: pd.DataFrame, weights: list[float]) -> pd.Series:
        """Return weighted portfolio return series."""
        weights_arr = np.array(weights)
        weights_arr = weights_arr / weights_arr.sum()
        return (returns * weights_arr).sum(axis=1)

    def analyze_instrument(
        self,
        code: str,
        window: int = 252,
        end_date: date | None = None,
        confidence: float = 0.95,
    ) -> dict[str, Any]:
        """Compute risk metrics for a single instrument."""
        returns_df = self._load_returns([code], window=window, end_date=end_date)
        if returns_df.empty:
            return {"error": f"Insufficient price data for {code}"}

        series = returns_df[code]
        return self._compute_metrics(series, confidence=confidence, code=code)

    def analyze_portfolio(
        self,
        codes: list[str],
        weights: list[float] | None = None,
        window: int = 252,
        end_date: date | None = None,
        confidence: float = 0.95,
    ) -> dict[str, Any]:
        """Compute risk metrics for a weighted portfolio."""
        if len(codes) < 2:
            return {"error": "Portfolio analysis requires at least 2 codes"}

        returns_df = self._load_returns(codes, window=window, end_date=end_date)
        if returns_df.empty or len(returns_df) < 2:
            return {"error": "Insufficient price data for portfolio analysis"}

        missing = [c for c in codes if c not in returns_df.columns]
        if missing:
            return {"error": f"Missing return data for: {missing}"}

        if weights is None:
            weights = [1.0 / len(codes)] * len(codes)
        if len(weights) != len(codes):
            return {"error": "weights length must match codes length"}

        portfolio = self._portfolio_returns(returns_df[codes], weights)
        result = self._compute_metrics(portfolio, confidence=confidence)
        result["codes"] = codes
        result["weights"] = [round(w, 6) for w in weights]

        # Per-instrument contribution to portfolio volatility
        cov = returns_df[codes].cov() * 252
        weights_arr = np.array(weights)
        port_var = weights_arr @ cov.values @ weights_arr
        if port_var > 0:
            marginal = cov.values @ weights_arr
            contributions = weights_arr * marginal / np.sqrt(port_var)
            result["volatility_contribution_pct"] = {
                code: round(float(c) * 100, 2)
                for code, c in zip(codes, contributions)
            }

        return result

    def _compute_metrics(
        self,
        returns: pd.Series,
        confidence: float = 0.95,
        code: str | None = None,
    ) -> dict[str, Any]:
        """Compute volatility, drawdown, VaR and ES for a return series."""
        returns = returns.dropna()
        if len(returns) < 2:
            return {"error": "At least 2 return observations required"}

        # Annualized volatility (%)
        daily_vol = returns.std()
        annual_vol = daily_vol * np.sqrt(252) * 100

        # Cumulative return for max drawdown
        cum = (1 + returns).cumprod()
        running_max = cum.cummax()
        drawdown = (cum - running_max) / running_max
        max_dd = drawdown.min() * 100

        alpha = 1 - confidence
        sorted_returns = returns.sort_values()

        # Historical VaR / ES
        var_idx = int(np.floor(alpha * len(sorted_returns)))
        var_hist = sorted_returns.iloc[max(var_idx, 0)] * 100
        es_hist = sorted_returns.iloc[: max(var_idx, 1)].mean() * 100

        # Parametric VaR / ES (assuming normal distribution).
        # Use scipy.stats.norm.ppf for the exact analytical z-score at the
        # requested confidence level; no Monte-Carlo sample is required.
        from scipy.stats import norm

        z = abs(norm.ppf(alpha))
        var_param = -(returns.mean() - z * daily_vol) * 100
        es_param = -(returns.mean() - (norm.pdf(z) / alpha) * daily_vol) * 100

        result: dict[str, Any] = {
            "confidence": confidence,
            "observations": len(returns),
            "annualized_volatility_pct": round(float(annual_vol), 2),
            "max_drawdown_pct": round(float(max_dd), 2),
            "var_historical_pct": round(float(-var_hist), 2),
            "es_historical_pct": round(float(-es_hist), 2),
            "var_parametric_pct": round(float(var_param), 2),
            "es_parametric_pct": round(float(es_param), 2),
        }
        if code:
            result["code"] = code
        return result
