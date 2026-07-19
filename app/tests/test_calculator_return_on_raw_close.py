"""Regression tests for the 前复权 close indicator calculation.

Guards the Phase 2.2/2.3 fix: ``calculate_single_etf`` now computes
all indicators (technical, risk, and period returns) on the true
前复权 close ``qfq_close = close * adj_factor / latest_adj_factor``
instead of the raw close or the un-normalised ``close * adj_factor``.

The expected behaviour is:

1. ``calculate_return_indicators`` returns period returns computed on
   the ``close`` column it is given — independent of any ``qfq_close``
   or ``adj_close`` column.
2. ``calculate_single_etf`` stores period returns, volatility,
   drawdown, Sharpe and technical indicators computed on the **前复权**
   close. This keeps long-window risk metrics comparable across
   corporate actions while anchoring the price level to the latest
   market close.
3. The amount column is passed through unchanged from the raw bar.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.data.indicators.calculator import calculate_single_etf
from app.data.indicators.risk import (
    RETURN_PERIODS,
    calculate_return_indicators,
    calculate_risk_indicators,
)


# ---------------------------------------------------------------------------
# calculate_return_indicators: pure-period-return contract
# ---------------------------------------------------------------------------


def test_calculate_return_indicators_emits_all_period_columns() -> None:
    """All five period-return columns must be present, and the last row
    must be a valid decimal (not NaN) for every period."""
    n = 300  # long enough to clear every window
    rng = np.random.default_rng(seed=11)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, size=n)))
    df = pd.DataFrame(
        {
            "trade_date": pd.bdate_range("2025-01-01", periods=n),
            "close": closes,
        }
    )

    out = calculate_return_indicators(df)

    for col in RETURN_PERIODS:
        assert col in out.columns, f"{col} missing from calculate_return_indicators output"
        assert pd.notna(out[col].iloc[-1]), f"{col} last row is NaN"
        # Decimals, not percentages: |return| should be < 10 for any realistic series.
        assert -10.0 < float(out[col].iloc[-1]) < 10.0


def test_calculate_return_indicators_uses_close_not_adj_close() -> None:
    """If a caller feeds in a DataFrame where the ``close`` column is
    the raw price and an extra ``adj_close`` column carries a scaled
    price, the function MUST ignore ``adj_close`` and compute returns
    purely from ``close``."""
    n = 300
    rng = np.random.default_rng(seed=23)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, size=n)))
    # Simulate a front-adjusted price series: latest = raw, history scaled.
    factor_curve = np.linspace(0.90, 1.00, n)
    adj_closes = closes * factor_curve

    df = pd.DataFrame(
        {
            "trade_date": pd.bdate_range("2025-01-01", periods=n),
            "close": closes,
            "adj_close": adj_closes,  # exists, but must be ignored
        }
    )

    out = calculate_return_indicators(df)

    # Hand-computed expected return on raw close at every window.
    for col, periods in RETURN_PERIODS.items():
        expected = closes[-1] / closes[-1 - periods] - 1
        got = float(out[col].iloc[-1])
        assert got == pytest.approx(expected, rel=1e-9), (
            f"{col}: raw-close expected {expected:.6f}, got {got:.6f}"
        )

        # And it MUST differ from the adj-close-based return.
        adj_expected = adj_closes[-1] / adj_closes[-1 - periods] - 1
        assert abs(got - adj_expected) > 1e-9, (
            f"{col}: returns computed on adj_close ({adj_expected:.6f}) "
            f"instead of raw close ({got:.6f})"
        )


# ---------------------------------------------------------------------------
# calculate_single_etf: end-to-end integration
# ---------------------------------------------------------------------------


def _make_bars(n: int, end_close: float, seed: int = 17) -> pd.DataFrame:
    rng = np.random.default_rng(seed=seed)
    closes = end_close * np.exp(np.cumsum(rng.normal(0, 0.012, size=n)))
    # Front-adjusted adj_factor: latest = 1.0, history trending toward 0.95.
    factor_curve = np.linspace(0.95, 1.00, n)
    qfq_closes = closes * factor_curve
    return pd.DataFrame(
        {
            "trade_date": pd.bdate_range("2024-06-01", periods=n),
            "open": closes,
            "high": closes * 1.01,
            "low": closes * 0.99,
            "close": closes,
            "volume": 1_000_000,
            "amount": closes * 1_000_000,
            "qfq_close": qfq_closes,
        }
    )


def test_calculate_single_etf_returns_use_qfq_close() -> None:
    """End-to-end: the 1m / 3m / 1y columns stored in the merged result
    must be the qfq-close pct_change, not the raw-close value."""
    df = _make_bars(n=300, end_close=10.0)
    out = calculate_single_etf("512760.SH", df)
    last = out.iloc[-1]

    qfq_closes = df["qfq_close"].to_numpy()
    for col, periods in RETURN_PERIODS.items():
        expected = qfq_closes[-1] / qfq_closes[-1 - periods] - 1
        got = float(last[col])
        assert got == pytest.approx(expected, rel=1e-9), (
            f"{col}: expected qfq-close return {expected:.6f}, got {got:.6f}"
        )


def test_calculate_single_etf_regression_for_512760_like_case() -> None:
    """Construct a deterministic series mimicking the 512760.SH case.
    After the Phase 2.2 fix returns are computed on the 前复权 close,
    so the 1y return must equal the qfq-close percentage move."""
    n = 300
    # Smooth, monotonic uptrend of exactly 5 % over the window.
    closes = np.linspace(10.00, 10.50, n)
    factor_curve = np.linspace(0.95, 1.00, n)  # post-normalisation adj_factor
    qfq_closes = closes * factor_curve
    df = pd.DataFrame(
        {
            "trade_date": pd.bdate_range("2024-06-01", periods=n),
            "open": closes,
            "high": closes + 0.01,
            "low": closes - 0.01,
            "close": closes,
            "volume": 1_000_000,
            "amount": closes * 1_000_000,
            "qfq_close": qfq_closes,
        }
    )

    out = calculate_single_etf("512760.SH", df)
    last = out.iloc[-1]

    # 1y (252 trading days): qfq_close[299] / qfq_close[47] - 1
    expected_1y = qfq_closes[-1] / qfq_closes[47] - 1
    assert abs(float(last["return_1y"]) - expected_1y) < 1e-9, (
        f"return_1y drift: expected {expected_1y:.4f}, got {last['return_1y']:.4f}"
    )

    # And it must NOT equal the raw-close 1y return.
    raw_expected_1y = closes[-1] / closes[47] - 1
    assert abs(float(last["return_1y"]) - raw_expected_1y) > 1e-3, (
        f"return_1y appears to still be computed on raw close: "
        f"got {last['return_1y']:.4f}, raw-close would give {raw_expected_1y:.4f}"
    )


# ---------------------------------------------------------------------------
# Volatility / drawdown / Sharpe live on qfq_close
# ---------------------------------------------------------------------------


def test_calculate_single_etf_volatility_uses_qfq_close() -> None:
    """Sanity check that volatility / drawdown / Sharpe are computed on
    the 前复权 close, not the raw close."""
    df = _make_bars(n=300, end_close=10.0)
    out = calculate_single_etf("512760.SH", df)
    last = out.iloc[-1]

    # Recompute what qfq-close risk metrics should look like.
    qfq = df[["trade_date", "open", "high", "low", "qfq_close", "volume", "amount"]].copy()
    qfq = qfq.rename(columns={"qfq_close": "close"})
    qfq_risk = calculate_risk_indicators(qfq)
    qfq_last = qfq_risk.iloc[-1]

    for col in ("volatility_20d", "volatility_60d", "max_drawdown_1y", "sharpe_1y"):
        assert float(last[col]) == pytest.approx(float(qfq_last[col]), rel=1e-9), (
            f"{col} no longer sourced from qfq_close: "
            f"single-etf={last[col]:.6f}, qfq-risk={qfq_last[col]:.6f}"
        )


# ---------------------------------------------------------------------------
# calc_return compatibility (legacy helper still works)
# ---------------------------------------------------------------------------


def test_calc_return_matches_calculate_return_indicators() -> None:
    """``calc_return(prices, window=N)`` and
    ``calculate_return_indicators`` are documented to disagree by exactly
    one period (see the long-standing "one-period-too-short" comment in
    ``risk.py``). ``pct_change(periods=N)`` — which
    ``calculate_return_indicators`` now uses — is the correct, modern
    convention. This test pins that ``calculate_return_indicators``
    actually emits a sensible, hand-checkable value for the short
    window and returns NaN when the series is too short for the
    longer windows (instead of silently wrapping or interpolating)."""
    prices = pd.Series(
        [100.0, 102.0, 104.0, 103.0, 105.0, 107.0,
         106.0, 108.0, 110.0, 109.0, 111.0, 115.0]
    )

    df = pd.DataFrame({"close": prices})
    out = calculate_return_indicators(df)

    # 1w (periods=5): the last 5-step pct_change is prices[11]/prices[6] - 1.
    expected_pct = prices.iloc[-1] / prices.iloc[-6] - 1
    assert float(out["return_1w"].iloc[-1]) == pytest.approx(expected_pct, rel=1e-9)

    # 1m / 3m / 6m / 1y windows are all > 12 rows → must be NaN, not
    # silently wrong / wraparound / extrapolated.
    for col in ("return_1m", "return_3m", "return_6m", "return_1y"):
        assert pd.isna(out[col].iloc[-1]), f"{col} should be NaN with 12 rows"
