"""End-to-end tests for the 5 P2 fixes.

Each test exercises one specific P2 issue and verifies that the fix
behaves correctly on a seeded database.  Together they form a regression
net that prevents the issues from re-appearing.

The 5 fixes under test:
  P2-1: ``risk_analysis_service._compute_metrics`` no longer allocates a
        100,000-sample standard normal that is immediately discarded.
  P2-2: ``backtest_engine.run_backtest`` returns a structured
        ``{"error": "no_data"}`` sentinel when there are no bars,
        distinguishable from a clean backtest with zero trades.
  P2-3: ``signal_generator`` reads ``LOOKBACK_BUFFER`` from the module
        (no hard-coded ``+ 10`` literal), and the buffer is large enough
        to absorb weekends + multi-day holidays.
  P2-4: ``attribution_service.analyze_backtest`` no longer divides by 1
        to hide a near-zero total return — instead it reports ``None``
        for percentage-of-return fields and emits a warning.
  P2-5: ``paper_trading_service.get_pnl_summary`` no longer triggers a
        redundant ``SELECT * FROM paper_trade_position`` by delegating to
        ``update_market_values``.  Quotes are fetched once for all open
        positions and market values are refreshed in-place.
"""

from __future__ import annotations

import inspect
import logging
import math
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from app.services import (
    attribution_service,
    backtest_engine,
    paper_trading_service,
    risk_analysis_service,
    signal_generator,
)
from app.services.attribution_service import AttributionService
from app.services.backtest_engine import BacktestResult, run_backtest
from app.services.paper_trading_service import (
    PaperTradingError,
    PaperTradingService,
)
from app.services.risk_analysis_service import RiskAnalysisService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_etf_with_prices(db_session, code: str, prices: list[float], start: str = "2025-01-02"):
    """Insert a deterministic OHLCV series for one instrument."""
    from app.models.etf import ETFInfo, InstrumentDailyBar

    if not db_session.get(ETFInfo, code):
        db_session.add(ETFInfo(code=code, name=code, market="SH", status="active"))
        db_session.commit()

    dates = pd.bdate_range(start, periods=len(prices))
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


def _seed_backtest_result(
    db_session,
    strategy_config,
    *,
    total_return: float,
    trades: list[dict] | None = None,
    etf_code: str = "510300.SH",
):
    """Insert a BacktestResult with a controllable total_return value."""
    from app.models.etl import BacktestResult

    br = BacktestResult(
        user_id=strategy_config.user_id,
        strategy_id=strategy_config.id,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 6, 30),
        metrics={
            "initial_capital": 100000.0,
            "final_nav": 100000.0 * (1 + total_return / 100),
            "total_return": total_return,
            "annualized_return": total_return,
            "max_drawdown": -5.0,
            "sharpe_ratio": 1.5,
            "win_rate": 50.0,
            "trade_count": len(trades) if trades else 0,
            "trading_days": 120,
        },
        trades=trades or [],
        config_snapshot={"etf_code": etf_code, "strategy_type": "momentum"},
    )
    db_session.add(br)
    db_session.commit()
    # Seed price history so benchmark-return lookup succeeds
    _seed_etf_with_prices(db_session, etf_code, [100 * (1.001 ** i) for i in range(120)])
    return br


def _provider(price: float) -> MagicMock:
    """Build a BinanceProvider mock that returns ``price`` for every quote."""
    df = pd.DataFrame(
        [
            {
                "etf_code": "BTC.US",
                "price": price,
                "price_change_pct": 0.0,
                "high": price,
                "low": price,
                "volume": 0,
                "amount": 0,
            }
        ]
    )
    mock = MagicMock()
    mock.fetch_realtime_quotes.return_value = df
    return mock


# ---------------------------------------------------------------------------
# P2-1: risk_analysis_service dead code removed
# ---------------------------------------------------------------------------


def test_p2_1_risk_analysis_has_no_dead_random_sample_source():
    """The unused 100k-sample np.random.standard_normal must be gone.

    We grep the source for the call and for the unused local
    ``z_score`` variable that previously held the Monte-Carlo estimate.
    """
    src = inspect.getsource(risk_analysis_service)
    assert "np.random.standard_normal" not in src, (
        "Dead np.random.standard_normal(100000) call must be removed"
    )
    # The unused local was named ``z_score`` and is no longer assigned.
    # Other modules also use ``z_score`` (e.g. mean-reversion) so we only
    # forbid a standalone assignment without subsequent use inside the
    # risk service.  A robust check: no line ``z_score =`` appears in the
    # file.
    assert "z_score =" not in src, (
        "Unused z_score local assignment should be removed"
    )


def test_p2_1_risk_analysis_still_produces_parametric_var(db_session):
    """Removing the dead code must not regress parametric VaR output."""
    rng = np.random.default_rng(11)
    prices = (100 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, 200)))).tolist()
    end_date = _seed_etf_with_prices(db_session, "P21.SH", prices)[1]

    svc = RiskAnalysisService(db_session)
    result = svc.analyze_instrument("P21.SH", window=200, end_date=end_date)

    assert "error" not in result
    # Parametric VaR should be a positive, finite percentage
    var_param = result["var_parametric_pct"]
    es_param = result["es_parametric_pct"]
    assert math.isfinite(var_param)
    assert math.isfinite(es_param)
    assert var_param > 0
    # ES >= VaR at the same confidence level
    assert es_param >= var_param


# ---------------------------------------------------------------------------
# P2-2: backtest empty returns structured "no_data" sentinel
# ---------------------------------------------------------------------------


def test_p2_2_backtest_empty_returns_structured_no_data_sentinel(db_session):
    """When there is no price data, metrics must carry the ``no_data`` error.

    The test also asserts that the result is distinguishable from a clean
    backtest that produced zero trades: the former has ``error`` set,
    the latter does not.
    """
    # 1. No data -> structured error
    result_empty = run_backtest(
        etf_code="NOPE_P22.SH",
        strategy_type="momentum",
        params={"momentum_window": 20, "threshold": 0.05, "holding_period": 20},
        start_date=date(2025, 1, 1),
        end_date=date(2025, 3, 1),
        initial_capital=100_000.0,
        db=db_session,
    )
    assert "error" in result_empty.metrics
    assert result_empty.metrics["error"] == BacktestResult.NO_DATA_ERROR
    assert result_empty.metrics["error"] == "no_data"
    assert result_empty.daily_nav == []
    assert result_empty.trades == []
    # And the sentinel is exposed at class level for callers to compare against
    assert BacktestResult.NO_DATA_ERROR == "no_data"


def test_p2_2_backtest_zero_trades_does_not_look_like_no_data(db_session, strategy_config):
    """A backtest that loaded data but found no entry signal should NOT carry the error.

    We construct a perfectly flat series so the momentum signal never
    fires.  The result should have the documented metrics but no
    ``error`` key.
    """
    flat = [100.0] * 60
    start, end = _seed_etf_with_prices(db_session, "FLAT.SH", flat)

    result = run_backtest(
        etf_code="FLAT.SH",
        strategy_type="momentum",
        params={"momentum_window": 20, "threshold": 0.05, "holding_period": 20},
        start_date=start,
        end_date=end,
        initial_capital=100_000.0,
        db=db_session,
    )
    # The result has the normal metric shape, not the no_data sentinel
    assert "error" not in result.metrics, (
        f"Zero-trade backtest must not look like a no-data error: {result.metrics}"
    )
    assert result.metrics.get("trade_count") == 0
    assert result.metrics.get("total_return") == 0.0


# ---------------------------------------------------------------------------
# P2-3: signal_generator LOOKBACK_BUFFER constant
# ---------------------------------------------------------------------------


def test_p2_3_signal_generator_exposes_lookback_buffer_constant():
    """``LOOKBACK_BUFFER`` must be a module-level constant, large enough."""
    assert hasattr(signal_generator, "LOOKBACK_BUFFER")
    assert isinstance(signal_generator.LOOKBACK_BUFFER, int)
    # 10 was the old magic number; we want a buffer that comfortably
    # covers weekends + multi-day holidays (>= 20 calendar days).
    assert signal_generator.LOOKBACK_BUFFER >= 20, (
        f"LOOKBACK_BUFFER={signal_generator.LOOKBACK_BUFFER} should be >= 20"
    )


def test_p2_3_signal_generator_no_magic_plus_10_in_source():
    """The source must not contain the old literal ``+ 10`` offset."""
    src = inspect.getsource(signal_generator)
    # Look for the specific call site that used to read
    # ``lookback_days + 10``.  After the refactor it must reference the
    # constant instead.
    assert "lookback_days + LOOKBACK_BUFFER" in src, (
        "generate_signals_for_strategy should add LOOKBACK_BUFFER, not a magic 10"
    )
    # And the literal ``+ 10`` on the lookback line is gone.  We allow
    # ``+ 10`` to appear elsewhere in the file but not on the same line
    # as ``lookback_days``.
    for line in src.splitlines():
        if "lookback_days" in line and "Timedelta" in line:
            assert "+ 10" not in line, (
                f"Old +10 buffer is still in: {line!r}"
            )


def test_p2_3_signal_generator_buffer_picks_up_data_across_long_holiday(db_session):
    """With LOOKBACK_BUFFER=30 the function must still see enough bars
    even if the requested trade_date is several calendar days after the
    last bar (simulating a long holiday).
    """
    code = "P23.SH"
    _seed_etf_with_prices(db_session, code, [100 * (1.01 ** i) for i in range(60)])
    # Pretend today is well past the last bar
    signals = signal_generator.generate_signals_for_strategy(
        db_session,
        etf_code=code,
        strategy_type="momentum",
        params={"momentum_window": 20, "threshold": 0.05},
        trade_date=date(2025, 4, 30),
        lookback_days=60,
    )
    # Strong uptrend => BUY.  Crucially we are not asserting the function
    # *fails*; we are asserting it has enough data thanks to the bigger
    # buffer.
    assert signals, "Expected at least one signal with the larger buffer"
    assert signals[0]["type"] in {"BUY", "HOLD"}


# ---------------------------------------------------------------------------
# P2-4: attribution_service no longer hides near-zero total return
# ---------------------------------------------------------------------------


def test_p2_4_attribution_no_silent_division_by_one(db_session, strategy_config):
    """When total_return is effectively zero, the summary fields must be None."""
    br = _seed_backtest_result(db_session, strategy_config, total_return=0.0)

    svc = AttributionService(db_session)
    result = svc.analyze_backtest(br.id)

    assert "error" not in result
    # The three pct-of-return fields must be None, not 0.0 — 0.0 would
    # be a *valid* answer and indistinguishable from "everything was 0".
    summary = result["summary"]
    for key in ("allocation_pct", "selection_pct", "interaction_pct"):
        assert key in summary, f"Missing {key} in summary"
        assert summary[key] is None, (
            f"{key} should be None for zero total_return, got {summary[key]!r}"
        )


def test_p2_4_attribution_logs_warning_for_near_zero_total_return(
    db_session, strategy_config, caplog
):
    """A WARNING must be emitted so the silent fall-back is observable."""
    br = _seed_backtest_result(
        db_session, strategy_config, total_return=1e-9  # below epsilon
    )

    svc = AttributionService(db_session)
    with caplog.at_level(logging.WARNING, logger=attribution_service.logger.name):
        svc.analyze_backtest(br.id)

    assert any(
        "total_return" in rec.message and "None" in rec.message
        for rec in caplog.records
    ), "Expected a warning mentioning total_return and None"


def test_p2_4_attribution_still_computes_pct_for_nonzero_total_return(
    db_session, strategy_config
):
    """The fix must not regress the normal case where total_return is non-trivial."""
    br = _seed_backtest_result(
        db_session,
        strategy_config,
        total_return=14.0,
        trades=[
            {
                "entry_date": "2024-02-01",
                "exit_date": "2024-02-15",
                "pnl_pct": 0.10,
            }
        ],
    )

    svc = AttributionService(db_session)
    result = svc.analyze_backtest(br.id)

    summary = result["summary"]
    for key in ("allocation_pct", "selection_pct", "interaction_pct"):
        assert summary[key] is not None, f"{key} should be a number for non-zero return"


def test_p2_4_attribution_source_no_silent_division_by_one():
    """The old ``denominator = total_return if total_return != 0 else 1`` must be gone."""
    src = inspect.getsource(attribution_service)
    # The specific failing pattern was a denominator that silently
    # substituted 1 for zero total_return.  We look for the substring
    # that uniquely identified the bug (``total_return if total_return
    # != 0 else 1``) so the test isn't fooled by an unrelated ``else 1.0``
    # in a different expression.
    assert "total_return if total_return != 0 else 1" not in src, (
        "Old silent divide-by-1 fallback must be removed"
    )
    # The new constant should be present
    assert "ZERO_RETURN_EPSILON" in src


# ---------------------------------------------------------------------------
# P2-5: paper_trading get_pnl_summary no longer double-queries positions
# ---------------------------------------------------------------------------


def test_p2_5_paper_trading_pnl_summary_does_not_call_update_market_values(db_session, crypto_universe):
    """get_pnl_summary must NOT delegate to update_market_values (which
    re-queries the position table).  We assert the call count stays at
    zero on a freshly created account (no positions => no Binance calls
    needed either).
    """
    svc = PaperTradingService(db_session)
    account = svc.create_account("P25", Decimal("10000"), user_id=1)

    with patch.object(svc, "update_market_values") as mock_update, patch.object(
        PaperTradingService, "_get_provider_for_code", return_value=_provider(100.0)
    ):
        svc.get_pnl_summary(account.id)

    mock_update.assert_not_called()


def test_p2_5_paper_trading_pnl_summary_one_batched_quote_call(db_session, crypto_universe):
    """With multiple open positions across different instruments, the
    Binance provider must be hit exactly once (one batched quote request),
    not once per position.
    """
    svc = PaperTradingService(db_session)
    account = svc.create_account("P25B", Decimal("100000"), user_id=1)

    # Open positions on both BTC.US and ETH.US so the symbol set is plural
    with patch.object(PaperTradingService, "_get_provider_for_code", return_value=_provider(100.0)):
        svc.place_order(account.id, "BTC.US", "BUY", Decimal("0.5"))
        svc.place_order(account.id, "ETH.US", "BUY", Decimal("1.0"))
    # After the two BUYs, both positions have avg_cost = 100.

    # Build a provider mock that returns different prices per symbol
    quotes_df = pd.DataFrame(
        [
            {"etf_code": "BTC.US", "price": 110.0, "price_change_pct": 0.0,
             "high": 110.0, "low": 110.0, "volume": 0, "amount": 0},
            {"etf_code": "ETH.US", "price": 220.0, "price_change_pct": 0.0,
             "high": 220.0, "low": 220.0, "volume": 0, "amount": 0},
        ]
    )
    multi_mock = MagicMock()
    multi_mock.fetch_realtime_quotes.return_value = quotes_df

    with patch.object(PaperTradingService, "_get_provider_for_code", return_value=multi_mock):
        summary = svc.get_pnl_summary(account.id)

    # Exactly one batched fetch
    assert multi_mock.fetch_realtime_quotes.call_count == 1
    call_args, _ = multi_mock.fetch_realtime_quotes.call_args
    symbols_arg = call_args[0]
    assert set(symbols_arg) == {"BTC.US", "ETH.US"}, (
        f"Expected both symbols in the single batched fetch, got {symbols_arg}"
    )

    # And the resulting unrealized PnL is correctly populated
    # Both positions were bought at 100.  Now BTC=110, ETH=220.
    # BTC: 0.5 * (110 - 100) = 5;  ETH: 1.0 * (220 - 100) = 120
    # Total unrealized = 125
    assert float(summary["unrealized_pnl"]) == pytest.approx(125.0, rel=1e-6)


def test_p2_5_paper_trading_pnl_summary_still_returns_zero_when_provider_fails(
    db_session, crypto_universe
):
    """If the Binance provider raises, get_pnl_summary must still return
    a coherent dict (the previous behaviour swallowed provider errors
    too).  We assert the contract is preserved.
    """
    svc = PaperTradingService(db_session)
    account = svc.create_account("P25C", Decimal("10000"), user_id=1)

    with patch.object(PaperTradingService, "_get_provider_for_code", return_value=_provider(100.0)):
        svc.place_order(account.id, "BTC.US", "BUY", Decimal("0.1"))

    broken_mock = MagicMock()
    broken_mock.fetch_realtime_quotes.side_effect = RuntimeError("binance down")

    with patch.object(PaperTradingService, "_get_provider_for_code", return_value=broken_mock):
        summary = svc.get_pnl_summary(account.id)

    # The summary structure must still be intact
    assert summary["account_id"] == account.id
    assert summary["trade_count"] == 1
    # And it shouldn't raise
    assert summary["unrealized_pnl"] is not None
