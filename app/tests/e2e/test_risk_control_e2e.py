"""End-to-end test for RiskControl.

Exercises the per-order, daily-loss, and circuit-breaker flows on a seeded
LiveTradeConfig.  Does not touch the network (Binance client is None).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.risk_control import CircuitBreaker, RiskCheckResult, RiskControl


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_circuit_breaker():
    """Reset the global CircuitBreaker state before each test."""
    CircuitBreaker._tripped.clear()
    yield
    CircuitBreaker._tripped.clear()


@pytest.fixture
def settings():
    """Settings instance with trading globally enabled."""
    from app.config import Settings

    return Settings(binance_trading_enabled=True)


# ---------------------------------------------------------------------------
# Allow / reject under normal conditions
# ---------------------------------------------------------------------------


def test_risk_control_allows_normal_order(db_session, live_config, settings):
    """A normal BUY order below the per-order limit should be allowed."""
    rc = RiskControl(db_session, live_config, settings)
    result = rc.check_order(
        instrument_code="BTC.US",
        side="BUY",
        quantity=Decimal("0.1"),
        price=Decimal("50"),  # 0.1 * 50 = 5 USDT, well below max=100
        order_type="LIMIT",
    )
    assert isinstance(result, RiskCheckResult)
    assert result.allowed is True


def test_risk_control_rejects_global_switch_disabled(db_session, live_config):
    """Master switch off -> all orders rejected."""
    from app.config import Settings

    settings = Settings(binance_trading_enabled=False)
    rc = RiskControl(db_session, live_config, settings)
    result = rc.check_order("BTC.US", "BUY", Decimal("0.1"), Decimal("50"))
    assert result.allowed is False
    assert "disabled" in result.reason.lower()


# ---------------------------------------------------------------------------
# Per-order value limit
# ---------------------------------------------------------------------------


def test_risk_control_rejects_oversized_order(db_session, live_config, settings):
    """An order exceeding max_order_value=100 should be rejected."""
    rc = RiskControl(db_session, live_config, settings)
    result = rc.check_order(
        "BTC.US", "BUY", Decimal("1"), Decimal("200")  # notional = 200 > 100
    )
    assert result.allowed is False
    assert "max" in result.reason.lower() or "exceeds" in result.reason.lower()


# ---------------------------------------------------------------------------
# Symbol allowlist
# ---------------------------------------------------------------------------


def test_risk_control_rejects_symbol_not_in_allowlist(db_session, live_config, settings):
    """A symbol not in allowed_symbols should be rejected."""
    rc = RiskControl(db_session, live_config, settings)
    result = rc.check_order(
        "DOGE.US",  # not in ['BTC.US', 'ETH.US']
        "BUY",
        Decimal("0.1"),
        Decimal("50"),
    )
    assert result.allowed is False
    assert "not in the allowed symbols" in result.reason


# ---------------------------------------------------------------------------
# Daily loss / circuit breaker
# ---------------------------------------------------------------------------


def test_risk_control_trips_circuit_breaker_on_daily_loss(db_session, live_config, settings):
    """A realised daily loss > max_daily_loss should trip the circuit breaker."""
    from datetime import datetime

    from app.models.trading import LiveTradePosition

    # NOTE: the service's _today_start() returns a tz-aware datetime but the
    # SQLAlchemy/SQLite column stores naive datetimes, so the comparison
    # ``updated_at >= today_start`` strips the tz. We therefore set
    # updated_at to a clearly-future naive datetime to guarantee the row
    # is included by the daily-loss query.
    far_future = datetime(2099, 12, 31)
    pos = LiveTradePosition(
        config_id=live_config.id,
        instrument_code="BTC.US",
        quantity=Decimal("0"),
        avg_cost=Decimal("0"),
        realized_pnl=Decimal("-200"),  # far exceeds max_daily_loss=50
        updated_at=far_future,
    )
    db_session.add(pos)
    db_session.commit()

    rc = RiskControl(db_session, live_config, settings)
    result = rc.check_order("BTC.US", "BUY", Decimal("0.01"), Decimal("50"))
    assert result.allowed is False
    assert "Daily loss" in result.reason

    # Circuit breaker should now be tripped
    tripped, reason = CircuitBreaker.is_tripped(live_config.id)
    assert tripped is True
    assert reason is not None


def test_circuit_breaker_blocks_subsequent_orders(db_session, live_config, settings):
    """Once tripped, all subsequent orders are rejected (until manual reset)."""
    from datetime import datetime

    from app.models.trading import LiveTradePosition

    db_session.add(
        LiveTradePosition(
            config_id=live_config.id,
            instrument_code="BTC.US",
            quantity=Decimal("0"),
            avg_cost=Decimal("0"),
            realized_pnl=Decimal("-100"),
            updated_at=datetime(2099, 12, 31),
        )
    )
    db_session.commit()

    rc = RiskControl(db_session, live_config, settings)
    first = rc.check_order("BTC.US", "BUY", Decimal("0.01"), Decimal("50"))
    assert first.allowed is False
    assert "Daily loss" in first.reason

    # After tripping, the circuit breaker pre-emptively rejects all orders
    # without re-running the daily-loss check
    second = rc.check_order("BTC.US", "BUY", Decimal("0.01"), Decimal("50"))
    assert second.allowed is False
    assert "tripped" in second.reason.lower() or "Circuit" in second.reason

    # Manual reset clears the trip; with the loss still present the order
    # is re-rejected by the daily-loss rule, but at least we know the
    # breaker itself was cleared
    rc.reset_circuit_breaker()
    tripped, _ = CircuitBreaker.is_tripped(live_config.id)
    assert tripped is False


# ---------------------------------------------------------------------------
# Risk status snapshot
# ---------------------------------------------------------------------------


def test_risk_control_get_risk_status(db_session, live_config, settings):
    """get_risk_status returns a dict with the documented fields."""
    rc = RiskControl(db_session, live_config, settings)
    status = rc.get_risk_status()
    expected_keys = {
        "config_id",
        "circuit_breaker_active",
        "circuit_breaker_reason",
        "orders_today",
        "realized_pnl_today",
        "last_error",
    }
    assert expected_keys.issubset(status.keys())
    assert status["config_id"] == live_config.id
    assert status["circuit_breaker_active"] is False
    assert status["orders_today"] == 0
