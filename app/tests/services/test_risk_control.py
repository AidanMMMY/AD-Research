"""Tests for RiskControl and CircuitBreaker.

Uses a mock Settings object instead of real environment configuration
so the master trading switch can be toggled on/off per test.
"""

from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.config import Settings
from app.models.trading import LiveTradeConfig, LiveTradeOrder, LiveTradePosition
from app.services.risk_control import (
    CircuitBreaker,
    RiskCheckResult,
    RiskControl,
)


# RiskControl._today_start() is anchored in Asia/Shanghai.
# We use the same zone in fixtures so SQLite compares consistently.
_TZ = ZoneInfo("Asia/Shanghai")


@pytest.fixture(autouse=True)
def _reset_circuit_breaker():
    """Reset the class-level CircuitBreaker state before every test.

    The breaker is a process-global dict keyed by config_id; without
    this fixture a previous test's trip would leak into the next one.
    """
    CircuitBreaker._tripped.clear()
    yield
    CircuitBreaker._tripped.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(trading_enabled: bool = True) -> Settings:
    """Build a Settings instance with the master switch toggled."""
    s = Settings()
    s.binance_trading_enabled = trading_enabled
    s.binance_market_order_slippage = 0.001
    return s


def _make_config(**overrides) -> LiveTradeConfig:
    defaults = dict(
        user_id=1,
        name="test-config",
        is_testnet=True,
        is_enabled=True,
        max_order_value=Decimal("100"),
        max_daily_loss=Decimal("500"),
        max_daily_orders=20,
        allowed_symbols=None,
    )
    defaults.update(overrides)
    return LiveTradeConfig(**defaults)


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------


def test_circuit_breaker_default_not_tripped():
    CircuitBreaker.reset(99)  # ensure clean state
    tripped, reason = CircuitBreaker.is_tripped(99)
    assert tripped is False
    assert reason is None


def test_circuit_breaker_trip_then_reset():
    CircuitBreaker.trip(101, "test reason")
    tripped, reason = CircuitBreaker.is_tripped(101)
    assert tripped is True
    assert "test reason" in reason
    CircuitBreaker.reset(101)
    tripped, _ = CircuitBreaker.is_tripped(101)
    assert tripped is False


# ---------------------------------------------------------------------------
# RiskControl.check_order – global switch
# ---------------------------------------------------------------------------


def test_global_switch_disabled_rejects(db_session):
    cfg = _make_config()
    db_session.add(cfg)
    db_session.commit()

    rc = RiskControl(db_session, cfg, _make_settings(trading_enabled=False))
    result = rc.check_order(
        "BTC.US", "BUY", Decimal("0.01"), Decimal("30000")
    )
    assert result.allowed is False
    assert "Trading is disabled" in result.reason


def test_basic_allow_when_under_limits(db_session):
    cfg = _make_config()
    db_session.add(cfg)
    db_session.commit()

    rc = RiskControl(db_session, cfg, _make_settings(trading_enabled=True))
    result = rc.check_order(
        "BTC.US", "BUY", Decimal("0.001"), Decimal("1000")
    )
    assert result.allowed is True
    assert result.reason == ""


# ---------------------------------------------------------------------------
# Per-order value limit
# ---------------------------------------------------------------------------


def test_order_value_above_max_rejects(db_session):
    cfg = _make_config(max_order_value=Decimal("100"))
    db_session.add(cfg)
    db_session.commit()

    rc = RiskControl(db_session, cfg, _make_settings())
    result = rc.check_order(
        "BTC.US", "BUY", Decimal("1"), Decimal("500")
    )
    assert result.allowed is False
    assert "exceeds max" in result.reason


# ---------------------------------------------------------------------------
# Daily order count
# ---------------------------------------------------------------------------


def test_daily_order_count_breach_trips_breaker(db_session):
    cfg = _make_config(max_daily_orders=2)
    db_session.add(cfg)
    db_session.commit()

    # Add 2 filled orders today to hit the limit. Use Shanghai tz
    # so SQLite can compare against _today_start() correctly.
    now_local = datetime.now(_TZ)
    for i in range(2):
        db_session.add(
            LiveTradeOrder(
                config_id=cfg.id,
                instrument_code=f"X{i}.US",
                side="BUY",
                order_type="LIMIT",
                quantity=Decimal("1"),
                price=Decimal("10"),
                filled_quantity=Decimal("1"),
                status="filled",
                created_at=now_local,
            )
        )
    db_session.commit()

    CircuitBreaker.reset(cfg.id)
    rc = RiskControl(db_session, cfg, _make_settings())
    result = rc.check_order(
        "BTC.US", "BUY", Decimal("0.001"), Decimal("1000")
    )
    assert result.allowed is False
    assert "limit" in result.reason.lower()
    # Breaker should now be tripped
    tripped, _ = CircuitBreaker.is_tripped(cfg.id)
    assert tripped is True


# ---------------------------------------------------------------------------
# Symbol allowlist
# ---------------------------------------------------------------------------


def test_symbol_allowlist_rejects_unknown(db_session):
    cfg = _make_config(allowed_symbols='["BTC.US", "ETH.US"]')
    db_session.add(cfg)
    db_session.commit()

    rc = RiskControl(db_session, cfg, _make_settings())
    result = rc.check_order(
        "DOGE.US", "BUY", Decimal("0.001"), Decimal("100")
    )
    assert result.allowed is False
    assert "not in the allowed symbols" in result.reason


def test_symbol_allowlist_allows_listed(db_session):
    cfg = _make_config(allowed_symbols='["BTC.US"]')
    db_session.add(cfg)
    db_session.commit()

    rc = RiskControl(db_session, cfg, _make_settings())
    result = rc.check_order(
        "BTC.US", "BUY", Decimal("0.001"), Decimal("100")
    )
    assert result.allowed is True


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


def test_duplicate_order_within_window_rejects(db_session):
    cfg = _make_config()
    db_session.add(cfg)
    db_session.commit()

    # Add a recent order with same (config, code, side)
    db_session.add(
        LiveTradeOrder(
            config_id=cfg.id,
            instrument_code="BTC.US",
            side="BUY",
            order_type="LIMIT",
            quantity=Decimal("0.001"),
            price=Decimal("30000"),
            filled_quantity=Decimal("0"),
            status="pending",
            created_at=datetime.now(_TZ),
        )
    )
    db_session.commit()

    rc = RiskControl(db_session, cfg, _make_settings())
    result = rc.check_order(
        "BTC.US", "BUY", Decimal("0.001"), Decimal("30000")
    )
    assert result.allowed is False
    assert "Duplicate" in result.reason


# ---------------------------------------------------------------------------
# Daily loss limit
# ---------------------------------------------------------------------------


def test_daily_loss_limit_breach_rejects_and_trips(db_session):
    cfg = _make_config(max_daily_loss=Decimal("100"))
    db_session.add(cfg)
    db_session.commit()

    # Add a position touched today with realized loss > 100.
    # Use Shanghai tz so SQLite compares against _today_start() correctly.
    db_session.add(
        LiveTradePosition(
            config_id=cfg.id,
            instrument_code="BTC.US",
            quantity=Decimal("0"),
            avg_cost=Decimal("0"),
            realized_pnl=Decimal("-200"),
            updated_at=datetime.now(_TZ),
        )
    )
    db_session.commit()

    CircuitBreaker.reset(cfg.id)
    rc = RiskControl(db_session, cfg, _make_settings())
    result = rc.check_order(
        "BTC.US", "BUY", Decimal("0.001"), Decimal("100")
    )
    assert result.allowed is False
    assert "loss" in result.reason.lower()
    tripped, _ = CircuitBreaker.is_tripped(cfg.id)
    assert tripped is True


# ---------------------------------------------------------------------------
# RiskCheckResult helper methods
# ---------------------------------------------------------------------------


def test_risk_check_result_helpers():
    a = RiskCheckResult.allow()
    assert a.allowed is True
    assert a.reason == ""

    r = RiskCheckResult.reject("nope")
    assert r.allowed is False
    assert r.reason == "nope"
