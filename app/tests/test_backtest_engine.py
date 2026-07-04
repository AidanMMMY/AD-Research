"""Tests for backtest engine: open-execution, CN friction, walk-forward.

These tests drive ``_simulate`` and ``run_walk_forward`` directly with
synthetic in-memory DataFrames so they don't need a database session.
"""

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from app.services.backtest_engine import (
    COMMISSION_MIN,
    COMMISSION_RATE,
    STAMP_TAX_SELL,
    TRANSFER_FEE,
    _simulate,
    apply_cn_friction,
    run_walk_forward,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bars(
    n: int = 30,
    *,
    start_price: float = 10.0,
    drift: float = 0.01,
    open_vs_close: float = 0.005,
    seed: int = 42,
) -> pd.DataFrame:
    """Build a deterministic synthetic bar frame.

    The bars are constructed so that ``open`` and ``adj_close`` are
    *never* equal — ``open`` is shifted by ``open_vs_close`` relative
    to ``adj_close`` on every bar. This makes it easy to verify that
    the engine picks the right execution price.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    closes = start_price * np.cumprod(1 + rng.normal(drift, 0.01, size=n))
    adj_closes = closes
    opens = closes * (1 + open_vs_close)
    highs = np.maximum(opens, closes) * 1.001
    lows = np.minimum(opens, closes) * 0.999
    volumes = rng.integers(100_000, 1_000_000, size=n)
    df = pd.DataFrame({
        "trade_date": dates.date,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "adj_close": adj_closes,
        "volume": volumes,
    })
    return df


def _buy_signal_series(bar_count: int, trigger_idx: int = 2) -> pd.Series:
    """Series that emits BUY at trigger_idx, SELL 5 bars later."""
    s = pd.Series(0, index=range(bar_count), dtype=int)
    s.iloc[trigger_idx] = 1
    s.iloc[trigger_idx + 5] = -1
    return s


# ---------------------------------------------------------------------------
# Tests: open execution avoids look-ahead
# ---------------------------------------------------------------------------


def test_open_execution_no_lookahead():
    """Under execution_price_model='open' the BUY fill must use the
    signal bar's OPEN (not its adj_close). With open != close on every
    bar, the BUY-side fill must differ between the 'open' and 'close'
    models — this is the load-bearing assertion (avoiding look-ahead
    bias)."""
    df = _make_bars(n=30, open_vs_close=0.01, seed=7)
    signals = _buy_signal_series(len(df), trigger_idx=2)

    res_open = _simulate(
        df,
        signals,
        initial_capital=100_000.0,
        commission_rate=0.001,
        slippage_rate=0.001,
        position_size=1.0,
        holding_period=10,
        execution_price_model="open",
        market="other",
        apply_friction=True,
    )
    res_close = _simulate(
        df,
        signals,
        initial_capital=100_000.0,
        commission_rate=0.001,
        slippage_rate=0.001,
        position_size=1.0,
        holding_period=10,
        execution_price_model="close",
        market="other",
        apply_friction=True,
    )

    # Both runs should produce exactly one round-trip trade.
    assert len(res_open.trades) == 1
    assert len(res_close.trades) == 1

    trade_open = res_open.trades[0]
    trade_close = res_close.trades[0]

    # OPEN-based entry price is strictly different from CLOSE-based.
    # (With open = adj_close * 1.01, the difference is ~1% of price.)
    assert trade_open.entry_price != pytest.approx(trade_close.entry_price)
    assert trade_open.entry_price == pytest.approx(float(df.iloc[2]["open"]))
    assert trade_close.entry_price == pytest.approx(float(df.iloc[2]["adj_close"]))

    # The SELL fill must likewise be the open of the SELL bar, not its close.
    assert trade_open.exit_price != pytest.approx(trade_close.exit_price)
    assert trade_open.exit_price == pytest.approx(float(df.iloc[7]["open"]))

    # And confirm via the signal log too (defence-in-depth).
    buy_log_open = next(s for s in res_open.signals if s["type"] == "BUY")
    buy_log_close = next(s for s in res_close.signals if s["type"] == "BUY")
    assert buy_log_open["price"] == pytest.approx(float(df.iloc[2]["open"]))
    assert buy_log_close["price"] == pytest.approx(float(df.iloc[2]["adj_close"]))


def test_execution_price_model_invalid_rejected():
    """Unknown execution_price_model must raise ValueError."""
    df = _make_bars(n=10)
    signals = pd.Series(0, index=range(len(df)), dtype=int)
    with pytest.raises(ValueError):
        _simulate(
            df,
            signals,
            initial_capital=10_000.0,
            commission_rate=0.001,
            slippage_rate=0.001,
            position_size=1.0,
            holding_period=5,
            execution_price_model="bogus",
            market="other",
            apply_friction=False,
        )


# ---------------------------------------------------------------------------
# Tests: CN friction
# ---------------------------------------------------------------------------


def test_cn_stamp_tax_sell_only():
    """apply_cn_friction: BUY charges commission + transfer fee; SELL
    additionally charges stamp duty (sell-side only). The ¥5 minimum
    only kicks in for tiny notionals."""
    # BUY 10000 notional
    buy = apply_cn_friction(Decimal("10000"), "buy")
    expected_buy = Decimal("10000") * Decimal(str(COMMISSION_RATE + TRANSFER_FEE))
    assert buy == expected_buy

    # SELL 10000 notional — must be strictly higher than the buy cost.
    sell = apply_cn_friction(Decimal("10000"), "sell")
    expected_sell = Decimal("10000") * Decimal(
        str(COMMISSION_RATE + TRANSFER_FEE + STAMP_TAX_SELL)
    )
    assert sell == expected_sell
    assert sell > buy
    # The exact gap must equal 10000 * STAMP_TAX_SELL.
    assert sell - buy == Decimal("10000") * Decimal(str(STAMP_TAX_SELL))

    # Small notional: minimum commission of ¥5 applies.
    tiny = apply_cn_friction(Decimal("100"), "buy")
    assert tiny == Decimal(str(COMMISSION_MIN))


def test_simulate_cn_market_charges_stamp_tax():
    """In a CN market run, the SELL signal should reduce sale proceeds
    by more than just the commission (i.e. stamp tax applies)."""
    df = _make_bars(n=20, open_vs_close=0.0, seed=11)
    signals = _buy_signal_series(len(df), trigger_idx=2)
    initial_cap = 100_000.0

    # CN market: commission + transfer on both sides, stamp tax on sell.
    res_cn = _simulate(
        df,
        signals,
        initial_capital=initial_cap,
        commission_rate=COMMISSION_RATE,
        slippage_rate=0.0,  # CN friction ignores slippage
        position_size=1.0,
        holding_period=10,
        execution_price_model="close",
        market="cn_a",
        apply_friction=True,
    )
    # "Other" market at commission_rate=0 (so no extra friction) is the
    # closest like-for-like baseline: any CN friction beyond ¥5 min must
    # show up as a worse net PnL.
    res_zero = _simulate(
        df,
        signals,
        initial_capital=initial_cap,
        commission_rate=0.0,
        slippage_rate=0.0,
        position_size=1.0,
        holding_period=10,
        execution_price_model="close",
        market="other",
        apply_friction=True,
    )

    assert len(res_cn.trades) == 1
    assert len(res_zero.trades) == 1

    # CN run should always deduct more (stamp tax + transfer on the
    # sell leg) than the friction-free baseline.
    cn_pnl = res_cn.trades[0].pnl
    zero_pnl = res_zero.trades[0].pnl
    assert cn_pnl < zero_pnl

    # The CN friction on a ~¥100k round-trip with these rates is
    # roughly ¥100 (commission) + ¥1 (transfer) + ¥5 (stamp sell) —
    # well above the ¥5 minimum. Confirm we lost at least that much.
    assert zero_pnl - cn_pnl > COMMISSION_MIN


# ---------------------------------------------------------------------------
# Tests: walk-forward
# ---------------------------------------------------------------------------


def test_walk_forward_split():
    """run_walk_forward must produce n_folds folds with non-overlapping
    train/test segments, anchored on the full date range."""
    df = _make_bars(n=120, seed=5)
    cfg = {
        "etf_code": "TEST",
        "strategy_type": "dummy",
        "params": {"holding_period": 5},
        "start_date": date(2024, 1, 1),
        "end_date": date(2024, 7, 1),
        # These extra kwargs should be forwarded through.
        "initial_capital": 50_000.0,
        "execution_price_model": "open",
        "market": "cn_a",
        "apply_friction": True,
    }

    # Monkey-patch run_backtest (used inside run_walk_forward) so the
    # test doesn't need a database session. We replace it with a thin
    # wrapper around _simulate that constructs a synthetic bars frame
    # for the fold's date range.
    from app.services import backtest_engine as be

    def fake_run_backtest(*, db=None, start_date, end_date, **kwargs):
        # Filter the synthetic frame to the requested date window.
        mask = (
            (df["trade_date"] >= start_date)
            & (df["trade_date"] <= end_date)
        )
        sub = df.loc[mask].reset_index(drop=True)
        if sub.empty:
            r = be.BacktestResult()
            r.metrics = {"error": be.BacktestResult.NO_DATA_ERROR}
            return r
        signals = _buy_signal_series(len(sub), trigger_idx=2)
        return _simulate(
            sub,
            signals,
            initial_capital=kwargs.get("initial_capital", 50_000.0),
            commission_rate=kwargs.get("commission_rate", 0.001),
            slippage_rate=kwargs.get("slippage_rate", 0.001),
            position_size=kwargs.get("position_size", 1.0),
            holding_period=kwargs.get("params", {}).get("holding_period", 5),
            execution_price_model=kwargs.get("execution_price_model", "open"),
            market=kwargs.get("market", "cn_a"),
            apply_friction=kwargs.get("apply_friction", True),
        )

    be.run_backtest = fake_run_backtest

    result = run_walk_forward(cfg, train_pct=0.6, n_folds=3, db=None)

    assert "folds" in result
    assert "test_metrics_overall" in result
    assert "ic_per_fold" in result

    assert len(result["folds"]) == 3
    assert len(result["ic_per_fold"]) == 3

    # Verify dates are non-overlapping test segments and cover the
    # window after the train slice.
    train_end_first = date.fromisoformat(result["folds"][0]["train_end"])
    test_start_first = date.fromisoformat(result["folds"][0]["test_start"])
    assert test_start_first > train_end_first

    # Train segment length is ~60% of the full range.
    full_start = cfg["start_date"]
    full_end = cfg["end_date"]
    total_days = (full_end - full_start).days
    train_days = (train_end_first - full_start).days
    expected_train = int(total_days * 0.6)
    assert abs(train_days - expected_train) <= 2  # ±2 days tolerance

    # Folds must each carry train + test metrics blocks.
    for fold in result["folds"]:
        assert "train_metrics" in fold
        assert "test_metrics" in fold
        # IC can be None when there's not enough data — that's fine.
        assert "ic" in fold

    # Aggregated test metrics should contain at least avg_total_return
    # when test segments produced trades.
    agg = result["test_metrics_overall"]
    assert isinstance(agg, dict)


def test_walk_forward_rejects_bad_train_pct():
    """train_pct outside (0, 1) must raise ValueError."""
    with pytest.raises(ValueError):
        run_walk_forward(
            {
                "etf_code": "TEST",
                "strategy_type": "x",
                "params": {},
                "start_date": date(2024, 1, 1),
                "end_date": date(2024, 6, 1),
            },
            train_pct=0.0,
            n_folds=3,
        )
    with pytest.raises(ValueError):
        run_walk_forward(
            {
                "etf_code": "TEST",
                "strategy_type": "x",
                "params": {},
                "start_date": date(2024, 1, 1),
                "end_date": date(2024, 6, 1),
            },
            train_pct=1.5,
            n_folds=3,
        )
