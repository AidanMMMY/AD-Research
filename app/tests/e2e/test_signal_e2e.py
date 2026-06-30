"""End-to-end test for the signal generator.

Exercises generate_signals_for_strategy across momentum / mean_reversion / rsi
strategies on a seeded price history.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.services.signal_generator import generate_signals_for_strategy


# ---------------------------------------------------------------------------
# Seeded price history: clear uptrend and clear downtrend
# ---------------------------------------------------------------------------


def _seed_price_history(db_session, code: str, prices: list[float]):
    """Insert a deterministic OHLCV series for one instrument."""
    from app.models.etf import ETFInfo, InstrumentDailyBar
    from decimal import Decimal

    # Ensure ETFInfo row exists
    if not db_session.get(ETFInfo, code):
        db_session.add(
            ETFInfo(code=code, name=code, market="SH", status="active")
        )
        db_session.commit()

    # Build a business-day date index
    dates = pd.bdate_range("2025-01-02", periods=len(prices))
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
# Momentum strategy
# ---------------------------------------------------------------------------


def test_momentum_strategy_returns_buy_on_strong_uptrend(db_session):
    """Strong uptrend (20-day return > 5%) should produce a BUY signal."""
    # Build 60 trading days with a 20%+ price rise over the last 20 days
    base = np.linspace(100, 100, 40)
    uptrend = np.linspace(100, 130, 20)  # +30% over 20 days
    prices = np.concatenate([base, uptrend]).tolist()
    trade_date = _seed_price_history(db_session, "UP.SH", prices)

    signals = generate_signals_for_strategy(
        db_session,
        etf_code="UP.SH",
        strategy_type="momentum",
        params={"momentum_window": 20, "threshold": 0.05},
        trade_date=trade_date,
        lookback_days=80,
    )

    assert isinstance(signals, list)
    assert len(signals) >= 1
    sig = signals[0]
    assert "type" in sig
    assert "strength" in sig
    assert sig["type"] == "BUY", f"Expected BUY signal, got {sig['type']}"
    assert 0 <= sig["strength"] <= 100


def test_momentum_strategy_returns_sell_on_strong_downtrend(db_session):
    """Strong downtrend (20-day return < -5%) should produce a SELL signal."""
    base = np.linspace(100, 100, 40)
    downtrend = np.linspace(100, 70, 20)  # -30% over 20 days
    prices = np.concatenate([base, downtrend]).tolist()
    trade_date = _seed_price_history(db_session, "DOWN.SH", prices)

    signals = generate_signals_for_strategy(
        db_session,
        etf_code="DOWN.SH",
        strategy_type="momentum",
        params={"momentum_window": 20, "threshold": 0.05},
        trade_date=trade_date,
        lookback_days=80,
    )

    assert len(signals) >= 1
    assert signals[0]["type"] == "SELL", f"Expected SELL, got {signals[0]['type']}"


# ---------------------------------------------------------------------------
# RSI strategy
# ---------------------------------------------------------------------------


def test_rsi_strategy_returns_sell_when_overbought(db_session):
    """Strong uptrend with realistic noise drives RSI above 70 -> SELL signal.

    NOTE: calc_rsi replaces 0 avg_loss with NaN (see app/data/indicators/technical.py).
    To exercise the overbought branch we need at least one losing bar so
    avg_loss is non-zero. We use a strong drift (1.5/day) with 2% noise.
    """
    rng = np.random.default_rng(0)
    base = np.linspace(100, 200, 60)
    # 2% noise to ensure some losing days exist (5% noise makes RSI drop to ~63)
    prices = (base + rng.normal(0, 2.0, 60)).tolist()
    last_date = _seed_price_history(db_session, "OB.SH", prices)
    # trade_date must be the last bar date so the full series is included
    # in the lookback window
    trade_date = last_date

    signals = generate_signals_for_strategy(
        db_session,
        etf_code="OB.SH",
        strategy_type="rsi",
        params={"rsi_period": 14, "overbought": 70, "oversold": 30},
        trade_date=trade_date,
        lookback_days=80,
    )

    assert len(signals) >= 1
    sig = signals[0]
    assert sig["type"] in {"SELL", "BUY", "HOLD"}
    # Strong uptrend with 2% noise should still produce RSI > 70 -> SELL
    assert sig["type"] == "SELL", f"Expected SELL on overbought, got {sig['type']}"


def test_rsi_strategy_returns_buy_when_oversold(db_session):
    """Strong downtrend with tiny noise drives RSI below 30 -> BUY signal."""
    rng = np.random.default_rng(1)
    base = np.linspace(200, 100, 60)
    prices = (base + rng.normal(0, 2.0, 60)).tolist()
    last_date = _seed_price_history(db_session, "OS.SH", prices)
    trade_date = last_date

    signals = generate_signals_for_strategy(
        db_session,
        etf_code="OS.SH",
        strategy_type="rsi",
        params={"rsi_period": 14, "overbought": 70, "oversold": 30},
        trade_date=trade_date,
        lookback_days=80,
    )

    assert len(signals) >= 1
    assert signals[0]["type"] == "BUY", f"Expected BUY on oversold, got {signals[0]['type']}"


# ---------------------------------------------------------------------------
# Mean reversion strategy
# ---------------------------------------------------------------------------


def test_mean_reversion_returns_hold_on_stable_series(db_session):
    """Stable prices (z-score near 0) should produce HOLD or no extreme signal."""
    # Build a stable sine-wave series around 100
    x = np.linspace(0, 4 * np.pi, 60)
    prices = (100 + 2 * np.sin(x)).tolist()
    trade_date = _seed_price_history(db_session, "STABLE.SH", prices)

    signals = generate_signals_for_strategy(
        db_session,
        etf_code="STABLE.SH",
        strategy_type="mean_reversion",
        params={"lookback_window": 20, "z_score_threshold": 2.0},
        trade_date=trade_date,
        lookback_days=80,
    )

    assert len(signals) >= 1
    # Stable series -> z-score is small -> HOLD
    assert signals[0]["type"] == "HOLD", f"Expected HOLD on stable series, got {signals[0]['type']}"


# ---------------------------------------------------------------------------
# Empty / insufficient data
# ---------------------------------------------------------------------------


def test_signal_returns_empty_on_insufficient_data(db_session):
    """No prices in DB -> empty list (not an exception)."""
    # No seeded data for this code
    signals = generate_signals_for_strategy(
        db_session,
        etf_code="GHOST.SH",
        strategy_type="momentum",
        params={},
        trade_date=date(2025, 3, 1),
        lookback_days=60,
    )
    assert signals == []
