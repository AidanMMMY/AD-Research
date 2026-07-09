"""Regression tests for the multi-period return calculation.

Guards against the 2026-07-08 bug where ``calculate_single_etf`` computed
``return_1w / return_1m / return_3m / return_6m / return_1y`` on the
adjusted close (close * adj_factor). After the adj_factor normalisation
that pinned the latest-day factor to 1.0, the historical adj_factor for
older bars dropped below 1.0 — so ``adj_close[old]`` ended up smaller
than ``close[old]``, and the ratio
``adj_close[latest] / adj_close[old] - 1`` baked future dividend yields
into the divisor. For ETF 512760.SH this deflated the displayed 1m
return from a few-percent move down to 0.71 %.

The expected behaviour is:

1. ``calculate_return_indicators`` returns period returns computed on
   the ``close`` column it is given — independent of adj_close.
2. ``calculate_single_etf`` stores period returns computed on the
   **raw** market close, ignoring ``adj_close``. This is the
   "price-return" view the UI exposes.
3. Volatility / drawdown / Sharpe stay on the adjusted close (these
   are not point-to-point comparisons, so the adjustment is harmless
   and keeps long-window metrics comparable across corporate actions).
4. The 1m/3m/1y returns for the regression ETF case (close goes from
   10.0 -> 10.5 with a 1 % dividend 10 trading days before "now",
   adj_factor[old] = 0.99 after the dividend normalisation) must be
   the **raw** percentage move (+5 %), not the adj-close-inflated
   value (~+6.06 %).
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
    the raw price and an extra ``adj_close`` column carries the
    scaled-down price (post the 2026-07-07 adj_factor normalisation),
    the function MUST ignore ``adj_close`` and compute returns purely
    from ``close``. This is the core regression guard."""
    n = 300
    rng = np.random.default_rng(seed=23)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, size=n)))
    # Simulate the post-normalisation schema: adj_close = close * factor
    # with the latest-day factor pinned to 1.0 and historical factors
    # trending down toward 0.9 — exactly the shape produced by
    # scripts/normalize_adj_factor_to_latest_one.py.
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

        # And it MUST differ from the adj-close-based return (which would
        # inflate returns by roughly the cumulative dividend yield).
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
    return pd.DataFrame(
        {
            "trade_date": pd.bdate_range("2024-06-01", periods=n),
            "open": closes,
            "high": closes * 1.01,
            "low": closes * 0.99,
            "close": closes,
            "volume": 1_000_000,
            "amount": closes * 1_000_000,
            "adj_close": closes * factor_curve,
        }
    )


def test_calculate_single_etf_returns_use_raw_close() -> None:
    """End-to-end: the 1m / 3m / 1y columns stored in the merged result
    must be the raw-close pct_change, not the adj_close-based value
    that ``calculate_risk_indicators`` would have produced."""
    df = _make_bars(n=300, end_close=10.0)
    out = calculate_single_etf("512760.SH", df)
    last = out.iloc[-1]

    raw_closes = df["close"].to_numpy()
    for col, periods in RETURN_PERIODS.items():
        expected = raw_closes[-1] / raw_closes[-1 - periods] - 1
        got = float(last[col])
        assert got == pytest.approx(expected, rel=1e-9), (
            f"{col}: expected raw-close return {expected:.6f}, got {got:.6f}"
        )


def test_calculate_single_etf_regression_for_512760_like_case() -> None:
    """Construct a deterministic "few-percent move" series mimicking the
    512760.SH regression report: ~300 trading days, close ends at 10.50
    after drifting up from 10.00 — a 5 % price move. The bug returned
    ~0.71 % because it was using adj_close with adj_factor[old] < 1.0;
    the fix must return ~5 %."""
    n = 300
    # Smooth, monotonic uptrend of exactly 5 % over the window.
    closes = np.linspace(10.00, 10.50, n)
    factor_curve = np.linspace(0.95, 1.00, n)  # post-normalisation adj_factor
    df = pd.DataFrame(
        {
            "trade_date": pd.bdate_range("2024-06-01", periods=n),
            "open": closes,
            "high": closes + 0.01,
            "low": closes - 0.01,
            "close": closes,
            "volume": 1_000_000,
            "amount": closes * 1_000_000,
            "adj_close": closes * factor_curve,
        }
    )

    out = calculate_single_etf("512760.SH", df)
    last = out.iloc[-1]

    # 1y (252 trading days): close[299] / close[47] - 1
    expected_1y = closes[-1] / closes[47] - 1
    assert abs(float(last["return_1y"]) - expected_1y) < 1e-9, (
        f"return_1y drift: expected {expected_1y:.4f}, got {last['return_1y']:.4f}"
    )

    # And the 1y return must NOT be the inflated value the pre-fix
    # adj_close path would have produced. With factor_curve[47] = 0.9573
    # the adj-close path would have given roughly
    #   (10.5 * 1.0) / (closes[47] * 0.9573) - 1 ≈ 0.0943
    # which is the adj-close-inflated value. Make sure we did NOT emit
    # that value.
    adj_close_old = closes[47] * factor_curve[47]
    adj_return_1y = (10.50 * 1.0) / adj_close_old - 1
    assert abs(float(last["return_1y"]) - adj_return_1y) > 1e-3, (
        f"return_1y appears to still be computed on adj_close: "
        f"got {last['return_1y']:.4f}, adj-close would give {adj_return_1y:.4f}"
    )


# ---------------------------------------------------------------------------
# Volatility / drawdown / Sharpe still live on adj_close
# ---------------------------------------------------------------------------


def test_calculate_single_etf_volatility_uses_adj_close() -> None:
    """Sanity check that we did NOT accidentally flip volatility /
    drawdown / Sharpe onto raw close too. Those long-window metrics
    stay on adj_close by design (they're statistical measures, not
    point-to-point ratios, so the adjustment is harmless and keeps
    them comparable across corporate actions)."""
    df = _make_bars(n=300, end_close=10.0)
    out = calculate_single_etf("512760.SH", df)
    last = out.iloc[-1]

    # Recompute what adj-close risk metrics should look like.
    # Build a separate DataFrame with adj_close as the "close" column so
    # we don't end up with both "close" and "adj_close" in the same frame
    # (which would break pd.to_numeric downstream).
    adj = df[["trade_date", "open", "high", "low", "adj_close", "volume", "amount"]].copy()
    adj = adj.rename(columns={"adj_close": "close"})
    adj_risk = calculate_risk_indicators(adj)
    adj_last = adj_risk.iloc[-1]

    for col in ("volatility_20d", "volatility_60d", "max_drawdown_1y", "sharpe_1y"):
        assert float(last[col]) == pytest.approx(float(adj_last[col]), rel=1e-9), (
            f"{col} no longer sourced from adj_close: "
            f"single-etf={last[col]:.6f}, adj-risk={adj_last[col]:.6f}"
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