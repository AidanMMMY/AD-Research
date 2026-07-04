"""Unit tests for the rolling min_periods tightening in risk.py.

Covers the four behaviours added in the 2026-07-04 P0 fixes:

1. ``calculate_risk_indicators`` raises the long-window ``min_periods``
   for ``sharpe_1y`` / ``max_drawdown_1y`` from 20 to 60 (the
   ``RISK_LONG_MIN_PERIODS`` constant).
2. ``ensure_min_sample`` masks the entire series when
   ``days_since_listing < min_periods``.
3. ``ensure_min_sample`` keeps historical rows intact when
   ``days_since_listing is None`` (only the rolling-not-null gate fires).
4. ``ensure_min_sample`` masks individual rows where the trailing
   60-day window still has fewer than 60 non-null observations.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.data.indicators.risk import (
    RISK_LONG_MIN_PERIODS,
    calculate_risk_indicators,
    ensure_min_sample,
)


# ---------------------------------------------------------------------------
# Long-window min_periods tightening
# ---------------------------------------------------------------------------


def test_risk_long_min_periods_constant_is_60() -> None:
    """The long-window constant must be 60, not 20."""
    assert RISK_LONG_MIN_PERIODS == 60


def test_calculate_risk_indicators_uses_60_min_periods_for_long_metrics() -> None:
    """A 30-row DataFrame (between the old 20 and the new 60 thresholds)
    must NOT produce any non-null ``sharpe_1y`` / ``max_drawdown_1y``
    value. The previous V1 code would have started emitting values at
    row 21; after the fix, the first non-null is at row 60.
    """
    n = 30
    rng = np.random.default_rng(seed=42)
    closes = 1.0 + np.cumsum(rng.normal(0, 0.01, size=n))
    df = pd.DataFrame(
        {
            "trade_date": pd.date_range("2025-01-01", periods=n, freq="B"),
            "open": closes,
            "high": closes + 0.005,
            "low": closes - 0.005,
            "close": closes,
            "volume": np.full(n, 100_000),
        }
    )
    out = calculate_risk_indicators(df)

    sharpe = out["sharpe_1y"]
    max_dd = out["max_drawdown_1y"]
    # At least the first 59 rows must be NaN — only row 60 onwards can
    # possibly carry a value. This guards against the regression where
    # min_periods=20 would have started emitting values at row 21.
    assert sharpe.iloc[:59].isna().all(), (
        "sharpe_1y leaked values before row 60 — min_periods not tightened"
    )
    assert max_dd.iloc[:59].isna().all(), (
        "max_drawdown_1y leaked values before row 60 — min_periods not tightened"
    )


def test_calculate_risk_indicators_emits_values_after_window() -> None:
    """At 120 rows, the last row should carry a real ``sharpe_1y`` /
    ``max_drawdown_1y`` (assuming days_since_listing is None).
    """
    n = 120
    rng = np.random.default_rng(seed=123)
    closes = 1.0 + np.cumsum(rng.normal(0, 0.01, size=n))
    df = pd.DataFrame(
        {
            "trade_date": pd.date_range("2025-01-01", periods=n, freq="B"),
            "open": closes,
            "high": closes + 0.005,
            "low": closes - 0.005,
            "close": closes,
            "volume": np.full(n, 100_000),
        }
    )
    out = calculate_risk_indicators(df)

    assert pd.notna(out["sharpe_1y"].iloc[-1])
    assert pd.notna(out["max_drawdown_1y"].iloc[-1])


# ---------------------------------------------------------------------------
# ensure_min_sample: listing-age gate
# ---------------------------------------------------------------------------


def test_ensure_min_sample_masks_entire_series_when_listing_too_recent() -> None:
    """When ``days_since_listing`` is known and smaller than the window,
    the entire output series must be NaN — even though the rolling
    series may have valid values.
    """
    raw = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    out = ensure_min_sample(raw, min_periods=60, days_since_listing=30)
    assert out.isna().all()


def test_ensure_min_sample_keeps_history_when_listing_unknown() -> None:
    """When ``days_since_listing`` is None we must NOT throw and must
    NOT blanket-mask the series. Only the rolling-not-null gate fires,
    which preserves historical backfills that don't have list_date.
    The proof is that the tail of the series (rows 60+) keeps its values
    — only the leading warmup rows are masked by the rolling gate.
    """
    raw = pd.Series(
        [0.1] * 70  # 70 valid points — clears the 60-period rolling gate
    )
    out = ensure_min_sample(raw, min_periods=60, days_since_listing=None)
    # Tail (rows 60..69, 0-indexed) must be unmasked — that's the proof
    # that days_since_listing=None does NOT blanket-mask.
    assert not out.iloc[60:].isna().any(), (
        "list_date-less history should not be blanket-masked"
    )
    # Leading warmup (rows 0..58) is masked by the rolling-not-null
    # gate — that's expected and unrelated to the listing-age fix.
    assert out.iloc[:59].isna().all()


def test_ensure_min_sample_masks_short_rolling_window() -> None:
    """Even when ``days_since_listing`` is large enough, rows whose
    trailing 60-period window still has fewer than 60 non-null samples
    must be NaN. Here the trailing window only has 50 valid points.
    """
    raw = pd.Series([np.nan] * 50 + [0.1] * 50)  # first 50 NaN, last 50 valid
    out = ensure_min_sample(raw, min_periods=60, days_since_listing=365)
    # First 49 rows are masked because the trailing window lacks 60 points.
    # Last row must also be NaN — its trailing 60-window only has 50 valid pts.
    assert out.iloc[-1] != 0.1


def test_ensure_min_sample_passes_through_when_window_full() -> None:
    """Sanity check: 200 dense valid values + ample listing age ⇒ output
    is unchanged (no NaN mask).
    """
    raw = pd.Series(np.linspace(0.0, 1.0, 200))
    out = ensure_min_sample(raw, min_periods=60, days_since_listing=1000)
    # The first ~59 rows may still be NaN (rolling-not-null gate), but
    # the tail must preserve the original values.
    pd.testing.assert_series_equal(
        out.iloc[60:].reset_index(drop=True),
        raw.iloc[60:].reset_index(drop=True),
        check_names=False,
    )


# ---------------------------------------------------------------------------
# days_since_listing wiring into calculate_risk_indicators
# ---------------------------------------------------------------------------


def test_calculate_risk_indicators_listing_age_masks_new_listing() -> None:
    """End-to-end: a 200-row DataFrame paired with days_since_listing=30
    must produce all-NaN ``sharpe_1y`` / ``max_drawdown_1y``.
    """
    n = 200
    rng = np.random.default_rng(seed=7)
    closes = 1.0 + np.cumsum(rng.normal(0, 0.01, size=n))
    df = pd.DataFrame(
        {
            "trade_date": pd.date_range("2025-01-01", periods=n, freq="B"),
            "open": closes,
            "high": closes + 0.005,
            "low": closes - 0.005,
            "close": closes,
            "volume": np.full(n, 100_000),
        }
    )
    out = calculate_risk_indicators(df, days_since_listing=30)
    assert out["sharpe_1y"].isna().all()
    assert out["max_drawdown_1y"].isna().all()