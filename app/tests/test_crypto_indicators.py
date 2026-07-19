"""Crypto-specific indicator tests.

Validates that the indicator pipeline uses the ``CRYPTO`` market config:
365-day annualisation, calendar-day return windows (7/30/90/180/365), and
MA windows (7/14/30/90). These tests are pure pandas and do not need a DB.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.data.indicators.calculator import calculate_single_etf
from app.data.indicators.market_config import get_market_config
from app.data.indicators.risk import (
    calc_sharpe,
    calc_volatility,
    calculate_return_indicators,
    calculate_risk_indicators,
)


def _make_crypto_bars(n: int = 400, seed: int = 42) -> pd.DataFrame:
    """Generate a synthetic crypto daily-bar frame with qfq_close."""
    rng = np.random.default_rng(seed)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, size=n)))
    return pd.DataFrame(
        {
            "trade_date": pd.date_range("2023-01-01", periods=n, freq="D"),
            "open": closes * 0.995,
            "high": closes * 1.02,
            "low": closes * 0.98,
            "close": closes,
            "volume": 1_000_000,
            "amount": closes * 1_000_000,
            "qfq_close": closes,
            "adj_factor": 1.0,
        }
    )


# ---------------------------------------------------------------------------
# Market config sanity
# ---------------------------------------------------------------------------


def test_crypto_market_config_values() -> None:
    cfg = get_market_config("CRYPTO")
    assert cfg.annualization_factor == 365
    assert cfg.return_windows == {
        "return_1w": 7,
        "return_1m": 30,
        "return_3m": 90,
        "return_6m": 180,
        "return_1y": 365,
    }
    assert cfg.ma_windows == (7, 14, 30, 90)
    assert cfg.risk_long_window == 365
    assert cfg.risk_long_min_periods == 90


# ---------------------------------------------------------------------------
# calculate_single_etf (crypto)
# ---------------------------------------------------------------------------


def test_crypto_single_etf_return_windows() -> None:
    df = _make_crypto_bars(400)
    out = calculate_single_etf("BTC.US", df, market="CRYPTO")
    last = out.iloc[-1]
    qfq = df["qfq_close"].to_numpy()

    assert last["return_1w"] == pytest.approx(qfq[-1] / qfq[-8] - 1, rel=1e-9)
    assert last["return_1m"] == pytest.approx(qfq[-1] / qfq[-31] - 1, rel=1e-9)
    assert last["return_3m"] == pytest.approx(qfq[-1] / qfq[-91] - 1, rel=1e-9)
    assert last["return_6m"] == pytest.approx(qfq[-1] / qfq[-181] - 1, rel=1e-9)
    assert last["return_1y"] == pytest.approx(qfq[-1] / qfq[-366] - 1, rel=1e-9)


def test_crypto_single_etf_ma_windows() -> None:
    df = _make_crypto_bars(400)
    out = calculate_single_etf("BTC.US", df, market="CRYPTO")
    last = out.iloc[-1]
    qfq = df["qfq_close"].to_numpy()

    # Schema column names are fixed, but the lookback windows come from config.
    assert last["ma5"] == pytest.approx(qfq[-7:].mean(), rel=1e-9)
    assert last["ma10"] == pytest.approx(qfq[-14:].mean(), rel=1e-9)
    assert last["ma20"] == pytest.approx(qfq[-30:].mean(), rel=1e-9)
    assert last["ma60"] == pytest.approx(qfq[-90:].mean(), rel=1e-9)


def test_crypto_single_etf_volatility_uses_365_annualization() -> None:
    df = _make_crypto_bars(400)
    out = calculate_single_etf("BTC.US", df, market="CRYPTO")
    last = out.iloc[-1]
    qfq = df["qfq_close"]
    daily_returns = qfq.pct_change().tail(20)
    expected_vol = daily_returns.std() * np.sqrt(365)
    assert last["volatility_20d"] == pytest.approx(expected_vol, rel=1e-9)


def test_crypto_single_etf_sharpe_matches_risk_module() -> None:
    df = _make_crypto_bars(400)
    out = calculate_single_etf("BTC.US", df, market="CRYPTO")

    qfq_df = df[["trade_date", "open", "high", "low", "qfq_close", "volume", "amount"]].copy()
    qfq_df = qfq_df.rename(columns={"qfq_close": "close"})
    risk = calculate_risk_indicators(qfq_df, market="CRYPTO")

    assert out["sharpe_1y"].iloc[-1] == pytest.approx(risk["sharpe_1y"].iloc[-1], rel=1e-9)
    assert out["max_drawdown_1y"].iloc[-1] == pytest.approx(
        risk["max_drawdown_1y"].iloc[-1], rel=1e-9
    )


# ---------------------------------------------------------------------------
# Lower-level helpers
# ---------------------------------------------------------------------------


def test_crypto_calc_volatility_annualization_factor() -> None:
    rng = np.random.default_rng(7)
    returns = pd.Series(rng.normal(0.0005, 0.02, size=365))
    vol = calc_volatility(returns, window=365, annualization_factor=365)
    expected = returns.std() * np.sqrt(365)
    assert vol == pytest.approx(expected, rel=1e-9)


def test_crypto_calc_sharpe_annualization_factor() -> None:
    rng = np.random.default_rng(8)
    returns = pd.Series(rng.normal(0.0005, 0.02, size=365))
    sharpe = calc_sharpe(
        returns,
        annualization_factor=365,
        trading_days_per_year=365,
    )
    expected = (returns.mean() * 365 - 0.02) / (returns.std() * np.sqrt(365))
    assert sharpe == pytest.approx(expected, rel=1e-9)


def test_crypto_calculate_return_indicators_windows() -> None:
    df = _make_crypto_bars(400)
    close = df["close"]
    out = calculate_return_indicators(df, market="CRYPTO")

    assert out["return_1w"].iloc[-1] == pytest.approx(close.iloc[-1] / close.iloc[-8] - 1, rel=1e-9)
    assert out["return_1m"].iloc[-1] == pytest.approx(close.iloc[-1] / close.iloc[-31] - 1, rel=1e-9)
    assert out["return_1y"].iloc[-1] == pytest.approx(close.iloc[-1] / close.iloc[-366] - 1, rel=1e-9)


# ---------------------------------------------------------------------------
# Long-window min_periods for crypto (90)
# ---------------------------------------------------------------------------


def test_crypto_risk_long_metrics_masked_below_min_periods() -> None:
    """With 80 rows, the 365-day window has fewer than 90 observations, so
    long-window metrics must be NaN."""
    df = _make_crypto_bars(80)
    qfq_df = df[["trade_date", "open", "high", "low", "qfq_close", "volume", "amount"]].copy()
    qfq_df = qfq_df.rename(columns={"qfq_close": "close"})
    out = calculate_risk_indicators(qfq_df, market="CRYPTO")

    assert out["sharpe_1y"].isna().all()
    assert out["max_drawdown_1y"].isna().all()


def test_crypto_risk_long_metrics_emit_after_min_periods() -> None:
    """With 400 rows, the last row has a full 365-day window and clears
    the 90-period min_periods gate."""
    df = _make_crypto_bars(400)
    qfq_df = df[["trade_date", "open", "high", "low", "qfq_close", "volume", "amount"]].copy()
    qfq_df = qfq_df.rename(columns={"qfq_close": "close"})
    out = calculate_risk_indicators(qfq_df, market="CRYPTO")

    assert pd.notna(out["sharpe_1y"].iloc[-1])
    assert pd.notna(out["max_drawdown_1y"].iloc[-1])


# ---------------------------------------------------------------------------
# Backward compatibility: A-share default unchanged
# ---------------------------------------------------------------------------


def test_ashare_default_single_etf_unchanged() -> None:
    """Calling calculate_single_etf without an explicit market must still
    use the A-share windows and annualisation factor."""
    df = _make_crypto_bars(400)  # dates are daily, but we treat as A-share bars
    out = calculate_single_etf("512760.SH", df)
    last = out.iloc[-1]
    qfq = df["qfq_close"].to_numpy()

    assert last["return_1w"] == pytest.approx(qfq[-1] / qfq[-6] - 1, rel=1e-9)
    assert last["return_1m"] == pytest.approx(qfq[-1] / qfq[-22] - 1, rel=1e-9)
    assert last["ma5"] == pytest.approx(qfq[-5:].mean(), rel=1e-9)
    assert last["ma10"] == pytest.approx(qfq[-10:].mean(), rel=1e-9)
