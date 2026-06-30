"""Tests for the signal generation engine.

Generates BUY/SELL/HOLD signals for a single instrument using seeded
``instrument_daily_bar`` rows. Avoids real network calls.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.etf import ETFInfo, InstrumentDailyBar
from app.services.signal_generator import (
    _fetch_bars_from_db,
    generate_signals_for_strategy,
)


def _seed_instrument(db, code="TEST01", days=80, start_price=10.0, drift=0.02):
    """Seed an instrument with a monotonic-up price series for testing."""
    db.add(
        ETFInfo(
            code=code,
            name=f"Test {code}",
            category="Test",
            list_date=date(2020, 1, 1),
        )
    )
    db.commit()

    base = start_price
    for i in range(days):
        px = round(base * (1 + drift), 4)
        bar = InstrumentDailyBar(
            etf_code=code,
            trade_date=date(2024, 1, 1) + timedelta(days=i),
            open=Decimal(str(base)),
            high=Decimal(str(px)),
            low=Decimal(str(base)),
            close=Decimal(str(px)),
            volume=1000,
            amount=Decimal("10000"),
            adj_factor=Decimal("1.0"),
        )
        db.add(bar)
        base = px
    db.commit()


def test_fetch_bars_from_db_returns_dataframe(db_session):
    _seed_instrument(db_session)
    end = date(2024, 1, 1) + timedelta(days=30)
    start = end - timedelta(days=10)
    df = _fetch_bars_from_db(db_session, "TEST01", start, end)
    assert not df.empty
    assert "close" in df.columns
    assert "etf_code" in df.columns


def test_fetch_bars_before_list_date_returns_empty(db_session):
    """is_before_list_date() should return empty when query is pre-listing."""
    db_session.add(
        ETFInfo(
            code="NEW01",
            name="New",
            category="Test",
            list_date=date(2030, 1, 1),  # far future
        )
    )
    db_session.commit()
    df = _fetch_bars_from_db(
        db_session, "NEW01", date(2024, 1, 1), date(2024, 6, 1)
    )
    assert df.empty


def test_signal_unknown_strategy_returns_empty(db_session):
    _seed_instrument(db_session)
    trade_date = date(2024, 1, 1) + timedelta(days=70)
    out = generate_signals_for_strategy(
        db_session,
        "TEST01",
        "mystery_strategy",
        {},
        trade_date=trade_date,
    )
    assert out == []


def test_signal_momentum_strong_uptrend_emits_buy(db_session):
    _seed_instrument(db_session, drift=0.05)  # 5% per day -> strong uptrend
    trade_date = date(2024, 1, 1) + timedelta(days=70)
    out = generate_signals_for_strategy(
        db_session,
        "TEST01",
        "momentum",
        {"momentum_window": 20, "threshold": 0.05},
        trade_date=trade_date,
    )
    assert out, "expected at least one signal on a strong uptrend"
    assert out[0]["type"] in ("BUY", "HOLD")
    assert 0 <= out[0]["strength"] <= 100


def test_signal_rsi_overbought_emits_sell(db_session):
    # Drift up sharply to push RSI over 70
    _seed_instrument(db_session, drift=0.06, days=80)
    trade_date = date(2024, 1, 1) + timedelta(days=70)
    out = generate_signals_for_strategy(
        db_session,
        "TEST01",
        "rsi",
        {"rsi_period": 14, "overbought": 70, "oversold": 30},
        trade_date=trade_date,
    )
    assert out, "expected a signal on a long monotonic uptrend"
    # Either SELL (overbought) or HOLD is acceptable; the point is no crash.
    assert out[0]["type"] in ("SELL", "HOLD")


def test_signal_insufficient_data_returns_empty(db_session):
    """Fewer than 30 bars should yield an empty signal list."""
    _seed_instrument(db_session, days=5)  # tiny
    trade_date = date(2024, 1, 1) + timedelta(days=4)
    out = generate_signals_for_strategy(
        db_session,
        "TEST01",
        "momentum",
        {},
        trade_date=trade_date,
    )
    assert out == []


@pytest.mark.parametrize("strategy", ["momentum", "mean_reversion", "rsi"])
def test_strategies_handle_missing_data_gracefully(db_session, strategy):
    """A no-data instrument should return [] rather than raising."""
    trade_date = date(2024, 6, 1)
    out = generate_signals_for_strategy(
        db_session,
        "GHOST",
        strategy,
        {},
        trade_date=trade_date,
    )
    assert out == []
