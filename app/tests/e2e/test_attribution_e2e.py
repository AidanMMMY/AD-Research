"""End-to-end test for AttributionService.

Exercises Brinson-style attribution on a seeded BacktestResult.
"""

from __future__ import annotations

import math

import pytest

from app.services.attribution_service import AttributionService


# ---------------------------------------------------------------------------
# Full Brinson attribution on a seeded backtest
# ---------------------------------------------------------------------------


def test_attribution_analyze_backtest_returns_documented_fields(db_session, backtest_result):
    """analyze_backtest returns a dict with the documented Brinson fields."""
    svc = AttributionService(db_session)
    result = svc.analyze_backtest(backtest_result.id)

    # 1. No exception
    # 2. Output shape
    assert "error" not in result
    expected_top = {"backtest_id", "total_return", "benchmark_return", "excess_return", "attribution", "summary", "trade_stats"}
    assert expected_top.issubset(result.keys())
    assert isinstance(result["attribution"], dict)
    assert isinstance(result["summary"], dict)
    assert isinstance(result["trade_stats"], dict)

    # 3. Sanity: every numeric is finite
    for key in ("total_return", "benchmark_return", "excess_return"):
        v = result[key]
        assert isinstance(v, (int, float))
        assert not math.isnan(v)
        assert not math.isinf(v)

    # Excess return = total - benchmark
    assert result["excess_return"] == pytest.approx(
        result["total_return"] - result["benchmark_return"], rel=1e-6
    )

    # 4. Attribution dict has all three effects
    expected_effects = {"allocation_effect", "selection_effect", "interaction_effect"}
    assert expected_effects.issubset(result["attribution"].keys())

    # Trade stats match the seeded trades (3 trades: 2 winners, 1 loser)
    stats = result["trade_stats"]
    assert stats["total_trades"] == 3
    assert stats["winning_trades"] == 2
    assert stats["losing_trades"] == 1


def test_attribution_unknown_backtest_returns_error(db_session):
    """A non-existent backtest_id should return an error dict, not raise."""
    svc = AttributionService(db_session)
    result = svc.analyze_backtest(99999)
    assert "error" in result
    assert "not found" in result["error"]


def test_attribution_empty_trades_returns_zero_effects(db_session, strategy_config):
    """A backtest with no trades should return zeroed-out attribution effects."""
    from app.models.etl import BacktestResult

    br = BacktestResult(
        user_id=strategy_config.user_id,
        strategy_id=strategy_config.id,
        start_date=__import__("datetime").date(2024, 1, 1),
        end_date=__import__("datetime").date(2024, 6, 30),
        metrics={
            "total_return": 5.0,
            "trading_days": 120,
        },
        trades=[],
        config_snapshot={"etf_code": "510300.SH"},
    )
    db_session.add(br)
    db_session.commit()

    svc = AttributionService(db_session)
    result = svc.analyze_backtest(br.id)
    assert result["attribution"]["allocation_effect"] == 0
    assert result["attribution"]["selection_effect"] == 0
    assert result["attribution"]["interaction_effect"] == 0
    assert result["summary"]["in_market_pct"] == 0.0
    assert result["trade_stats"]["total_trades"] == 0


def test_attribution_in_market_pct_matches_actual_time_in_market(db_session, backtest_result):
    """in_market_pct should reflect the fraction of days actually in positions."""
    svc = AttributionService(db_session)
    result = svc.analyze_backtest(backtest_result.id)

    # Seeded trades:
    # 2024-02-01 to 2024-02-15  -> 15 days
    # 2024-03-01 to 2024-03-10  -> 10 days
    # 2024-04-01 to 2024-04-20  -> 20 days
    # Total in-market = 45 days
    # trading_days = 120  -> 45 / 120 = 37.5%
    assert result["summary"]["in_market_pct"] == pytest.approx(37.5, rel=1e-3)
