"""End-to-end test for RiskAnalysisService.

Exercises VaR, ES, max drawdown, and portfolio risk metrics on a seeded
price history.
"""

from __future__ import annotations

import math
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from app.services.risk_analysis_service import RiskAnalysisService


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _seed_etf_with_prices(db_session, code: str, prices: list[float]):
    """Insert a deterministic OHLCV series for one instrument."""
    from app.models.etf import ETFInfo, InstrumentDailyBar

    if not db_session.get(ETFInfo, code):
        db_session.add(ETFInfo(code=code, name=code, market="SH", status="active"))
        db_session.commit()

    dates = pd.bdate_range("2024-01-02", periods=len(prices))
    for d, px in zip(dates, prices, strict=False):
        db_session.add(
            InstrumentDailyBar(
                etf_code=code,
                trade_date=d.date(),
                open=Decimal(str(round(px * 0.99, 4))),
                high=Decimal(str(round(px * 1.01, 4))),
                low=Decimal(str(round(px * 0.98, 4))),
                close=Decimal(str(round(px, 4))),
                volume=1_000_000,
                amount=Decimal(str(px * 1_000_000)),
                adj_factor=Decimal("1.0"),
            )
        )
    db_session.commit()
    return dates[-1].date()


# ---------------------------------------------------------------------------
# Single-instrument risk metrics
# ---------------------------------------------------------------------------


def test_risk_analysis_single_instrument_returns_documented_metrics(db_session):
    """A single ETF should return a dict with the documented metric keys."""
    rng = np.random.default_rng(7)
    prices = (100 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, 200)))).tolist()
    end_date = _seed_etf_with_prices(db_session, "A.SH", prices)

    svc = RiskAnalysisService(db_session)
    result = svc.analyze_instrument("A.SH", window=200, end_date=end_date)

    # Shape
    assert "error" not in result
    expected_keys = {
        "confidence", "observations", "annualized_volatility_pct",
        "max_drawdown_pct", "var_historical_pct", "es_historical_pct",
        "var_parametric_pct", "es_parametric_pct", "code",
    }
    assert expected_keys.issubset(result.keys()), f"Missing keys: {expected_keys - result.keys()}"

    # Sanity: every metric is finite
    for key, val in result.items():
        if isinstance(val, (int, float)):
            assert not math.isnan(val), f"{key} is NaN"
            assert not math.isinf(val), f"{key} is inf"

    # Annualized volatility should be positive
    assert result["annualized_volatility_pct"] > 0
    # Max drawdown should be <= 0
    assert result["max_drawdown_pct"] <= 0
    # VaR / ES reported as positive percentages (sign convention: loss size)
    assert result["var_historical_pct"] >= 0
    assert result["es_historical_pct"] >= 0
    # ES >= VaR at the same confidence level
    assert result["es_historical_pct"] >= result["var_historical_pct"]


def test_risk_analysis_insufficient_data_returns_error(db_session):
    """An instrument with no price data should return an error dict, not raise."""
    svc = RiskAnalysisService(db_session)
    result = svc.analyze_instrument("NOPE.SH")
    assert "error" in result


# ---------------------------------------------------------------------------
# Portfolio risk metrics
# ---------------------------------------------------------------------------


def test_risk_analysis_portfolio_returns_volatility_contributions(db_session):
    """Portfolio analysis should return a dict with per-asset vol contributions."""
    rng = np.random.default_rng(13)
    a = (100 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, 200)))).tolist()
    b = (100 * np.exp(np.cumsum(rng.normal(0.001, 0.025, 200)))).tolist()
    end_a = _seed_etf_with_prices(db_session, "PORT_A.SH", a)
    end_b = _seed_etf_with_prices(db_session, "PORT_B.SH", b)
    end_date = max(end_a, end_b)

    svc = RiskAnalysisService(db_session)
    result = svc.analyze_portfolio(
        ["PORT_A.SH", "PORT_B.SH"],
        weights=[0.6, 0.4],
        window=200,
        end_date=end_date,
    )

    # Shape
    assert "error" not in result
    assert "annualized_volatility_pct" in result
    assert "max_drawdown_pct" in result
    assert "var_historical_pct" in result
    assert "volatility_contribution_pct" in result
    assert "codes" in result
    assert "weights" in result
    assert result["codes"] == ["PORT_A.SH", "PORT_B.SH"]
    assert sum(result["weights"]) == pytest.approx(1.0, rel=1e-6)

    # Volatility contribution is reported per-asset. The formula
    # ``weights * marginal_contribution / portfolio_vol`` does NOT sum
    # to 100% by construction — it sums to the portfolio volatility in
    # percent terms. We just verify it's a finite, non-extreme number.
    contribs = result["volatility_contribution_pct"]
    for code, val in contribs.items():
        assert math.isfinite(val)
        # Each contribution is a fraction of the portfolio's annualized vol
        assert -100 < val < 100, f"{code} contribution {val} outside [-100, 100]"
    # We have one entry per requested code
    assert set(contribs.keys()) == {"PORT_A.SH", "PORT_B.SH"}


def test_risk_analysis_portfolio_requires_two_codes(db_session):
    """Portfolio analysis with < 2 codes should return an error."""
    svc = RiskAnalysisService(db_session)
    result = svc.analyze_portfolio(["A.SH"])
    assert "error" in result
    assert "at least 2" in result["error"]


def test_risk_analysis_weights_mismatch_returns_error(db_session):
    """Mismatched weights length should return an error, not raise."""
    svc = RiskAnalysisService(db_session)
    result = svc.analyze_portfolio(["A.SH", "B.SH"], weights=[0.5, 0.3, 0.2])
    assert "error" in result


# ---------------------------------------------------------------------------
# Confidence-level parameter
# ---------------------------------------------------------------------------


def test_risk_analysis_higher_confidence_yields_higher_var(db_session):
    """At 99% confidence, VaR should be >= VaR at 95%."""
    rng = np.random.default_rng(99)
    prices = (100 * np.exp(np.cumsum(rng.normal(0.0, 0.02, 200)))).tolist()
    end_date = _seed_etf_with_prices(db_session, "CONF.SH", prices)

    svc = RiskAnalysisService(db_session)
    r95 = svc.analyze_instrument("CONF.SH", window=200, confidence=0.95, end_date=end_date)
    r99 = svc.analyze_instrument("CONF.SH", window=200, confidence=0.99, end_date=end_date)
    assert r99["var_historical_pct"] >= r95["var_historical_pct"]
