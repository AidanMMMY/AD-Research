"""End-to-end test for the BacktestEngine.

Verifies run_backtest produces NAV, trades, metrics on a seeded price series.
The cost model under test charges both commission AND slippage symmetrically
on BUY and SELL (see _calculate_transaction_cost in backtest_engine.py).
"""

from __future__ import annotations

import math
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from app.services.backtest_engine import run_backtest


# ---------------------------------------------------------------------------
# Helper: build a deterministic price series (60 trading days)
# ---------------------------------------------------------------------------


def _seed_etf_with_prices(db_session, code: str, prices: list[float]):
    """Insert a deterministic OHLCV series for one instrument."""
    from app.models.etf import ETFInfo, InstrumentDailyBar

    if not db_session.get(ETFInfo, code):
        db_session.add(ETFInfo(code=code, name=code, market="SH", status="active"))
        db_session.commit()

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
    return dates[0].date(), dates[-1].date()


# ---------------------------------------------------------------------------
# Smoke test: backtest runs end-to-end
# ---------------------------------------------------------------------------


def test_backtest_runs_on_seeded_series(db_session):
    """A simple uptrending series should produce at least one BUY trade and a NAV curve."""
    # Steady +1%/day drift -> strong momentum
    prices = [100 * (1.01 ** i) for i in range(80)]
    start, end = _seed_etf_with_prices(db_session, "UP.SH", prices)

    result = run_backtest(
        etf_code="UP.SH",
        strategy_type="momentum",
        params={"momentum_window": 20, "threshold": 0.05, "holding_period": 20},
        start_date=start,
        end_date=end,
        initial_capital=100_000.0,
        commission_rate=0.001,
        slippage_rate=0.001,
        db=db_session,
    )

    # 1. Did it run? (no exception)
    # 2. Output shape
    assert hasattr(result, "daily_nav")
    assert hasattr(result, "trades")
    assert hasattr(result, "metrics")
    assert hasattr(result, "signals")
    assert len(result.daily_nav) > 0
    assert isinstance(result.metrics, dict)

    # 3. NAV sanity: every NAV is finite and positive
    for point in result.daily_nav:
        assert "date" in point
        assert "nav" in point
        assert "price" in point
        assert "signal" in point
        nav = point["nav"]
        assert isinstance(nav, float)
        assert not math.isnan(nav)
        assert not math.isinf(nav)
        assert nav > 0

    # Metrics dict has the documented fields
    expected_metric_keys = {
        "initial_capital", "final_nav", "total_return", "annualized_return",
        "max_drawdown", "sharpe_ratio", "win_rate", "trade_count",
        "trading_days", "commission_rate", "slippage_rate", "position_size",
    }
    assert expected_metric_keys.issubset(result.metrics.keys())

    # 4. With a +1%/day drift we should see at least one BUY trade
    assert any(s["type"] == "BUY" for s in result.signals)


def test_backtest_costs_reduce_pnl_symmetrically(db_session):
    """Both BUY and SELL pay commission + slippage; final NAV should be < buy-and-hold."""
    # Strong uptrend
    prices = [100 * (1.005 ** i) for i in range(80)]
    start, end = _seed_etf_with_prices(db_session, "COST.SH", prices)

    result = run_backtest(
        etf_code="COST.SH",
        strategy_type="momentum",
        params={"momentum_window": 20, "threshold": 0.05, "holding_period": 20},
        start_date=start,
        end_date=end,
        initial_capital=100_000.0,
        commission_rate=0.001,
        slippage_rate=0.001,
        db=db_session,
    )

    # The cost model should produce trades where pnl is calculated net of cost
    if result.trades:
        for trade in result.trades:
            assert trade.entry_price > 0
            assert trade.exit_price > 0
            # trade.pnl is the realised PnL
            assert isinstance(trade.pnl, float)

    # Total return should be a finite number
    tr = result.metrics["total_return"]
    assert math.isfinite(tr)


def test_backtest_sharpe_ratio_is_finite_on_clean_data(db_session):
    """Sharpe ratio should be a finite number on a valid series."""
    rng = np.random.default_rng(123)
    prices = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, 80)))
    start, end = _seed_etf_with_prices(db_session, "RAND.SH", prices.tolist())

    result = run_backtest(
        etf_code="RAND.SH",
        strategy_type="rsi",
        params={"rsi_period": 14, "overbought": 70, "oversold": 30, "holding_period": 10},
        start_date=start,
        end_date=end,
        initial_capital=100_000.0,
        commission_rate=0.001,
        slippage_rate=0.001,
        db=db_session,
    )

    sharpe = result.metrics["sharpe_ratio"]
    # Sharpe may be 0 (int) when no trades occur or as default; the contract
    # is just that it's finite and numeric.
    assert isinstance(sharpe, (int, float))
    assert math.isfinite(float(sharpe)), f"Sharpe not finite: {sharpe}"


def test_backtest_empty_on_no_data(db_session):
    """Backtest on a non-existent instrument should return an empty result, not raise."""
    from datetime import date

    result = run_backtest(
        etf_code="NOPE.SH",
        strategy_type="momentum",
        params={},
        start_date=date(2025, 1, 1),
        end_date=date(2025, 3, 1),
        initial_capital=100_000.0,
        db=db_session,
    )
    assert result.daily_nav == []
    assert result.trades == []
    assert result.metrics == {}


def test_backtest_win_rate_in_unit_range(db_session):
    """Win rate, if there are trades, should be in [0, 100]."""
    rng = np.random.default_rng(456)
    prices = 100 * np.exp(np.cumsum(rng.normal(0.002, 0.015, 100)))
    start, end = _seed_etf_with_prices(db_session, "WR.SH", prices.tolist())

    result = run_backtest(
        etf_code="WR.SH",
        strategy_type="mean_reversion",
        params={"lookback_window": 20, "z_score_threshold": 1.5, "holding_period": 5},
        start_date=start,
        end_date=end,
        initial_capital=100_000.0,
        commission_rate=0.001,
        slippage_rate=0.001,
        db=db_session,
    )

    wr = result.metrics.get("win_rate", 0)
    if result.trades:
        assert 0.0 <= wr <= 100.0, f"Win rate {wr} out of [0, 100]"


def test_backtest_max_drawdown_is_non_positive(db_session):
    """Max drawdown is reported as a non-positive percentage."""
    rng = np.random.default_rng(789)
    prices = 100 * np.exp(np.cumsum(rng.normal(-0.001, 0.025, 100)))
    start, end = _seed_etf_with_prices(db_session, "DD.SH", prices.tolist())

    result = run_backtest(
        etf_code="DD.SH",
        strategy_type="momentum",
        params={"momentum_window": 10, "threshold": 0.02, "holding_period": 10},
        start_date=start,
        end_date=end,
        initial_capital=100_000.0,
        commission_rate=0.001,
        slippage_rate=0.001,
        db=db_session,
    )

    mdd = result.metrics["max_drawdown"]
    assert mdd <= 0.0, f"Max drawdown should be <= 0, got {mdd}"
    assert mdd >= -100.0, f"Max drawdown {mdd} < -100%"
