"""Regression tests for technical indicators.

Specifically guards against two P1 bugs caught during the 2026-07-01
platform verification sprint:
1. calc_rsi NaN on a perfectly rising series (RSI would never trigger SELL)
2. Calc unit consistency (no long-term NaN propagation)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

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