"""Tests for BacktestService.get_backtest's nav_summary field.

The nav_summary is a coarse NAV curve derived from the persisted trade
list — not persisted itself, computed on read. These tests cover the
two cases that matter for the frontend chart:

  1. With at least one closed trade → at least 3 points (start + per-trade
     exits) and the running NAV reflects cumulative realised PnL.
  2. With no trades → points=[] and a helpful note.
"""

from datetime import date

import pytest

from app.models.etl import BacktestResult, StrategyConfig
from app.services.backtest_service import BacktestService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strategy(session) -> StrategyConfig:
    """Insert the StrategyConfig row that BacktestResult FKs into."""
    cfg = StrategyConfig(
        name="nav-summary-test",
        strategy_type="ma_cross",
        params={},
        is_active=True,
    )
    session.add(cfg)
    session.commit()
    session.refresh(cfg)
    return cfg


def _make_backtest(
    session,
    *,
    trades: list[dict] | None,
    start_date: date = date(2024, 1, 1),
    initial_capital: float = 100000.0,
) -> BacktestResult:
    """Insert a BacktestResult row with the given trades JSON."""
    bt = BacktestResult(
        strategy_id=_make_strategy(session).id,
        start_date=start_date,
        end_date=date(2024, 6, 30),
        metrics={"initial_capital": initial_capital, "total_return": 0.0},
        trades=trades or [],
        config_snapshot={
            "etf_code": "510300",
            "strategy_type": "ma_cross",
            "params": {},
            "initial_capital": initial_capital,
        },
    )
    session.add(bt)
    session.commit()
    session.refresh(bt)
    return bt


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_nav_summary_with_trades(db_session):
    """Two closed trades → 1 start point + 2 exit points = 3 points."""
    trades = [
        {
            "entry_date": "2024-02-01",
            "exit_date": "2024-03-15",
            "entry_price": 10.0,
            "exit_price": 11.0,
            "side": "long",
            "pnl": 1500.0,
            "pnl_pct": 10.0,
        },
        {
            "entry_date": "2024-04-01",
            "exit_date": "2024-05-20",
            "entry_price": 11.5,
            "exit_price": 10.8,
            "side": "long",
            "pnl": -800.0,
            "pnl_pct": -6.96,
        },
    ]
    bt = _make_backtest(db_session, trades=trades)
    svc = BacktestService(db_session)

    result = svc.get_backtest(bt.id)

    assert result is not None
    assert "nav_summary" in result, "get_backtest must return nav_summary"

    nav = result["nav_summary"]
    assert nav["initial_capital"] == 100000.0
    assert "points" in nav and len(nav["points"]) == 3, (
        f"expected 3 points (start + 2 exits), got {len(nav['points'])}"
    )

    # Point 0: start at initial_capital on the backtest's start_date.
    start_point = nav["points"][0]
    assert start_point["date"] == date(2024, 1, 1).isoformat()
    assert start_point["nav"] == 100000.0
    assert start_point["kind"] == "start"

    # Point 1: after +1500 pnl.
    p1 = nav["points"][1]
    assert p1["date"] == "2024-03-15"
    assert p1["nav"] == pytest.approx(101500.0)
    assert p1["kind"] == "exit"
    assert p1["trade_pnl"] == pytest.approx(1500.0)

    # Point 2: after +1500 - 800 = +700 pnl.
    p2 = nav["points"][2]
    assert p2["date"] == "2024-05-20"
    assert p2["nav"] == pytest.approx(100700.0)
    assert p2["kind"] == "exit"
    assert p2["trade_pnl"] == pytest.approx(-800.0)

    # The note must clearly mark this as a derived, coarse curve.
    assert "简化 NAV" in nav["note"] or "trades" in nav["note"].lower()

    # Existing fields must not be removed or renamed.
    for key in ("id", "strategy_id", "start_date", "end_date",
                "metrics", "trades", "daily_nav", "config_snapshot",
                "created_at"):
        assert key in result, f"existing field {key!r} must still be present"


def test_nav_summary_no_trades(db_session):
    """Empty trades list → points=[] and a note explaining the empty curve."""
    bt = _make_backtest(db_session, trades=[])
    svc = BacktestService(db_session)

    result = svc.get_backtest(bt.id)

    assert result is not None
    nav = result["nav_summary"]
    assert nav["points"] == []
    assert nav["initial_capital"] == 100000.0
    assert "无交易记录" in nav["note"] or "不可用" in nav["note"]


def test_nav_summary_handles_missing_initial_capital(db_session):
    """Fallback to metrics.initial_capital when config_snapshot is empty."""
    bt = _make_backtest(db_session, trades=None, initial_capital=50000.0)
    # Wipe config_snapshot so the helper must fall back to metrics.
    bt.config_snapshot = {}
    db_session.commit()

    svc = BacktestService(db_session)
    nav = svc._compute_nav_summary_from_trades(bt)

    assert nav["initial_capital"] == 50000.0
    assert nav["points"] == []  # no trades → no points


def test_nav_summary_handles_open_trade(db_session):
    """A trade with exit_date=None still produces a terminal point with date=None."""
    trades = [
        {
            "entry_date": "2024-02-01",
            "exit_date": None,  # still open
            "entry_price": 10.0,
            "exit_price": None,
            "side": "long",
            "pnl": 0.0,
            "pnl_pct": 0.0,
        },
    ]
    bt = _make_backtest(db_session, trades=trades)
    svc = BacktestService(db_session)

    nav = svc._compute_nav_summary_from_trades(bt)

    assert len(nav["points"]) == 2
    assert nav["points"][1]["date"] is None
    assert nav["points"][1]["kind"] == "open"
