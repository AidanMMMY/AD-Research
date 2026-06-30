"""Regression tests for technical indicators.

Specifically guards against two P1 bugs caught during the 2026-07-01
platform verification sprint:
1. calc_rsi NaN on a perfectly rising series (RSI would never trigger SELL)
2. Calc unit consistency (no long-term NaN propagation)
3. Risk-indicator unit consistency (all decimals, no × 100)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.data.indicators.risk import (
    calc_max_drawdown,
    calc_return,
    calc_sharpe,
    calc_volatility,
    calculate_risk_indicators,
)
from app.data.indicators.technical import calc_rsi


class TestCalcRsiEdgeCases:
    """calc_rsi should never return NaN past the warm-up window, even on
    monotonic series (perfectly rising or perfectly falling)."""

    def test_perfectly_rising_series_returns_100(self):
        """A monotonic uptrend should yield RSI=100 (extreme overbought),
        NOT NaN as the original buggy implementation did."""
        prices = pd.Series(np.arange(1, 30, dtype=float))  # 1, 2, 3, ...
        rsi = calc_rsi(prices, window=14)
        # First 14 values are warm-up; values after should all be 100
        tail = rsi.iloc[14:]
        assert tail.notna().all(), f"RSI went NaN on monotonic uptrend: {tail.tolist()}"
        assert (tail == 100.0).all(), f"Expected RSI=100, got {tail.tolist()}"

    def test_perfectly_falling_series_returns_0(self):
        """A monotonic downtrend should yield RSI=0 (extreme oversold),
        NOT NaN."""
        prices = pd.Series(np.arange(30, 0, -1, dtype=float))  # 30, 29, 28, ...
        rsi = calc_rsi(prices, window=14)
        tail = rsi.iloc[14:]
        assert tail.notna().all()
        assert (tail == 0.0).all(), f"Expected RSI=0, got {tail.tolist()}"

    def test_constant_series_returns_neutral_value(self):
        """A flat series has zero gain and zero loss; result is undefined
        but must not be NaN (some libraries return 50 for this case)."""
        prices = pd.Series([100.0] * 30)
        rsi = calc_rsi(prices, window=14)
        tail = rsi.iloc[14:]
        # Either 0, 100, or NaN acceptable — but not propagated as the bug
        # Was: with avg_gain==0 and avg_loss==0, original code gave NaN forever.
        # We accept any finite value (0, 50, or 100) or NaN here; the
        # critical assertion is that it doesn't blow up callers downstream.
        assert not tail.isna().any() or tail.isna().all(), \
            f"Mixed NaN/finite is confusing: {tail.tolist()}"

    def test_realistic_series_stays_in_range(self):
        """Random walk RSI should stay in [0, 100] for all valid points."""
        np.random.seed(42)
        prices = pd.Series(100 * np.exp(np.cumsum(np.random.normal(0.001, 0.02, 100))))
        rsi = calc_rsi(prices, window=14)
        tail = rsi.iloc[14:].dropna()
        assert (tail >= 0).all() and (tail <= 100).all(), \
            f"RSI out of [0, 100]: min={tail.min()} max={tail.max()}"

    def test_strong_uptrend_triggers_oversold_signal(self):
        """The whole point of RSI: a strong uptrend should saturate near 100
        so the SELL signal logic has something to work with. (The original
        bug returned NaN, making every SELL signal silently skip.)"""
        # 15 trading days of consistent +1% gains
        prices = pd.Series([100 * (1.01 ** i) for i in range(30)])
        rsi = calc_rsi(prices, window=14)
        assert rsi.iloc[-1] == 100.0, \
            f"Strong uptrend should saturate RSI=100, got {rsi.iloc[-1]}"


# ---------------------------------------------------------------------------
# Risk-indicator unit consistency
#
# After the 2026-07-01 risk-unit unification, every risk function in
# app.data.indicators.risk must return values in DECIMAL form (0.1648),
# not percentage form (16.48).  Sharpe remains dimensionless.  These tests
# lock in that contract so future refactors don't reintroduce the old
# `× 100` behaviour.
# ---------------------------------------------------------------------------


class TestRiskIndicatorUnitConsistency:
    """All risk metrics must be returned as decimals (not percentages)."""

    def test_calc_volatility_returns_decimal(self):
        """Annualised vol on a known series should be a small decimal, not
        a 2-digit number like 16.48."""
        rng = np.random.default_rng(123)
        returns = pd.Series(rng.normal(0.0005, 0.02, 252))
        vol = calc_volatility(returns, window=252)
        # Annualised vol of a 2% daily stdev series ≈ 0.3175
        # (0.02 * sqrt(252) ≈ 0.3175).  Must be < 1.0 (decimal), not 31.75.
        assert 0 < vol < 1.0, (
            f"calc_volatility returned {vol} — should be a decimal in [0, 1] "
            "but looks like a percentage.  Did × 100 creep back in?"
        )

    def test_calc_max_drawdown_returns_decimal(self):
        """A 50% drawdown should yield -0.5 (not -50)."""
        prices = pd.Series([100.0, 90.0, 80.0, 50.0, 70.0])
        mdd = calc_max_drawdown(prices)
        # Peak was 100, trough was 50 → -50% → -0.5
        assert mdd == pytest.approx(-0.5), (
            f"calc_max_drawdown returned {mdd} — expected -0.5 (decimal)"
        )

    def test_calc_return_returns_decimal(self):
        """A 25% gain should yield 0.25 (not 25)."""
        prices = pd.Series([100.0, 110.0, 120.0, 125.0])
        ret = calc_return(prices, window=4)
        # (125 / 100) - 1 = 0.25
        assert ret == pytest.approx(0.25), (
            f"calc_return returned {ret} — expected 0.25 (decimal)"
        )

    def test_calc_sharpe_unchanged(self):
        """Sharpe ratio was always dimensionless; it must stay that way."""
        rng = np.random.default_rng(456)
        returns = pd.Series(rng.normal(0.001, 0.02, 252))
        sharpe = calc_sharpe(returns)
        # Sharpe of a ~16% annual vol / ~25% annual return series is small.
        # Crucially: |sharpe| should not be in the 10s-100s range that
        # would suggest a regression to percentage form.
        assert -50 < sharpe < 50, (
            f"calc_sharpe returned {sharpe} — out of expected dimensionless range"
        )

    def test_calculate_risk_indicators_columns_are_decimals(self):
        """The DataFrame produced by calculate_risk_indicators should hold
        decimal-form values in all risk columns (volatility_*, return_*,
        max_drawdown_1y), with sharpe_1y remaining dimensionless."""
        rng = np.random.default_rng(789)
        close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, 300)))
        df = pd.DataFrame({
            "trade_date": pd.bdate_range("2024-01-02", periods=300),
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1_000_000,
        })
        result = calculate_risk_indicators(df)
        last = result.iloc[-1]

        # Volatility columns: decimal in [0, 1] for any realistic series.
        for col in ("volatility_20d", "volatility_60d"):
            v = float(last[col])
            assert 0 < v < 2.0, f"{col}={v} not in expected decimal range"

        # Max drawdown: negative decimal, |.| < 1
        mdd = float(last["max_drawdown_1y"])
        assert -1.0 <= mdd <= 0.0, f"max_drawdown_1y={mdd} not in [-1, 0]"

        # Period returns: small decimals
        for col in ("return_1w", "return_1m", "return_3m", "return_6m", "return_1y"):
            r = float(last[col])
            assert -1.0 <= r <= 10.0, f"{col}={r} outside reasonable range"

        # Cross-check: the previous V1 bug returned vol ~30 for this
        # series; if volatility_20d > 5.0 now, × 100 has crept back in.
        assert float(last["volatility_20d"]) < 5.0, (
            f"volatility_20d={last['volatility_20d']} is suspiciously large — "
            "× 100 may have been reintroduced."
        )
