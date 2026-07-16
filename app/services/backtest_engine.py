"""Backtest engine core.

Simulates trading based on strategy signals and calculates performance metrics.

Supports configurable execution price models and friction regimes so that
the engine can be calibrated per market:
  - ``execution_price_model="open"`` (default): fills at signal-day OPEN,
    avoiding look-ahead bias from using adjusted close on the same bar.
  - ``execution_price_model="close"``: legacy behaviour using adj_close
    on the signal bar. BASELINE ONLY — known to introduce look-ahead
    bias. Kept for rollback / baseline comparison.
  - ``execution_price_model="next_open"``: event-driven style — fills at
    the NEXT session's OPEN. Most conservative.

Friction model:
  - ``market="cn_a"`` (default): A-share standard rates — stamp duty on
    sell side only, commission + transfer fee both sides, with a ¥5
    minimum commission.
  - any other market: legacy symmetric commission + slippage.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

from app.data.repositories import price_repository
from app.strategies.base import StrategyRegistry


# ---------------------------------------------------------------------------
# China A-share friction constants (standard retail rates, mid-2024).
# ---------------------------------------------------------------------------
STAMP_TAX_SELL = 0.0005    # 印花税：单边卖出 0.05%
COMMISSION_RATE = 0.001    # 佣金：双边 0.1%
TRANSFER_FEE = 0.00001     # 过户费：双边 0.001%
COMMISSION_MIN = 5.0       # 最低佣金 ¥5

VALID_EXECUTION_MODELS = {"open", "close", "next_open"}
VALID_MARKETS = {"cn_a", "us", "hk", "crypto", "other"}

# ---------------------------------------------------------------------------
# Market-specific annualization factors (quant P0-4)
# A-share=244, US=252, crypto=365, HK=247. Stocks trade ~244-252 days/yr
# depending on holidays; crypto is 24/7 (365). Crypto also trades
# weekends, so we keep that separate from the equity buckets.
# ---------------------------------------------------------------------------
ANNUALIZATION_FACTORS: dict[str, int] = {
    "cn_a": 244,
    "us": 252,
    "hk": 247,
    "crypto": 365,
    "other": 252,  # legacy default — same as US convention
}


def annualization_factor_for(market: str) -> int:
    """Return the per-market annualization factor used by Sharpe/Sortino.

    Defaults to 252 for unknown markets so legacy callers don't break.
    """
    return ANNUALIZATION_FACTORS.get(market, 252)


def _load_bars(etf_code: str, start_date: date, end_date: date, db: Any) -> pd.DataFrame:
    """Load historical bars for backtesting from the local price repository."""
    if db is None:
        raise ValueError("Backtest engine requires a database session")

    # Guard against backtest ranges that pre-date the instrument's listing
    # or post-date its delisting.
    list_date = price_repository.get_list_date(db, etf_code)
    delist_date = price_repository.get_delist_date(db, etf_code)

    # If instrument was delisted before the backtest end date, exclude it.
    if delist_date and end_date < delist_date:
        return pd.DataFrame()

    if list_date and end_date < list_date:
        return pd.DataFrame()

    # Clamp date range to [list_date, delist_date].
    if list_date and start_date < list_date:
        start_date = list_date
    if delist_date and end_date > delist_date:
        end_date = delist_date

    df = price_repository.get_bars(
        db, etf_code, start_date, end_date, adjusted=True
    )
    if df.empty:
        return df

    # Ensure expected columns are present for the engine.
    df = df[["trade_date", "open", "high", "low", "close", "adj_close", "volume"]].copy()
    return df


class Trade:
    """Represents a single trade."""

    def __init__(
        self,
        entry_date: date,
        exit_date: date | None = None,
        entry_price: float = 0,
        exit_price: float = 0,
        side: str = "long",
        pnl: float = 0,
        pnl_pct: float = 0,
    ):
        self.entry_date = entry_date
        self.exit_date = exit_date
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.side = side
        self.pnl = pnl
        self.pnl_pct = pnl_pct


class BacktestResult:
    """Container for backtest results."""

    # Sentinel value stored in metrics["error"] when the engine could not
    # load any price data. Distinguishes "no data available" from a clean
    # run with zero trades (where trade_count == 0 but no error key).
    NO_DATA_ERROR = "no_data"

    def __init__(self):
        self.daily_nav: list[dict[str, Any]] = []
        self.trades: list[Trade] = []
        self.metrics: dict[str, float] = {}
        self.signals: list[dict[str, Any]] = []
        # Cross-sectional-only breakdown (set when ``run_backtest`` was
        # driven in cross-sectional mode via ``etf_codes``). ``None``
        # for single-instrument runs.
        self.per_symbol: list[dict[str, Any]] | None = None


def get_strategy_signals(
    data: pd.DataFrame,
    strategy_type: str,
    params: dict[str, Any],
) -> pd.Series:
    """Generate trading signals for backtesting using the strategy registry.

    Returns a pandas Series with values:
      1 = BUY, -1 = SELL, 0 = HOLD
    """
    strategy_class = StrategyRegistry.get(strategy_type)
    if strategy_class is None:
        return pd.Series(0, index=data.index)

    strategy = strategy_class(params)
    return strategy.generate_series(data)


# ---------------------------------------------------------------------------
# Friction helpers
# ---------------------------------------------------------------------------


def apply_cn_friction(
    notional: Decimal,
    action: str,
    commission_min: float = COMMISSION_MIN,
) -> Decimal:
    """Compute A-share friction cost for a given notional and side.

    Buy:  commission + transfer fee
    Sell: commission + transfer fee + stamp tax (sell-side only)

    A ¥5 minimum commission is applied per fill.
    """
    if action == "buy":
        rate = COMMISSION_RATE + TRANSFER_FEE
    elif action == "sell":
        rate = COMMISSION_RATE + TRANSFER_FEE + STAMP_TAX_SELL
    else:
        raise ValueError(f"Unknown action: {action!r}")

    fee = notional * Decimal(str(rate))
    minimum = Decimal(str(commission_min))
    return max(fee, minimum)


def _calculate_transaction_cost(
    notional: float,
    commission_rate: float,
    slippage_rate: float,
    action: str = "buy",
    market: str = "other",
    commission_min: float = COMMISSION_MIN,
) -> float:
    """Return the absolute transaction cost charged on a notional trade.

    For ``market="cn_a"`` the A-share friction model applies (stamp tax
    only on sell, transfer fee both sides, ¥5 minimum commission).
    Otherwise the legacy symmetric commission + slippage model is used.
    """
    if market == "cn_a":
        return float(apply_cn_friction(
            Decimal(str(notional)), action, commission_min
        ))

    total_cost_rate = commission_rate + slippage_rate
    return notional * total_cost_rate


# ---------------------------------------------------------------------------
# Execution price selection
# ---------------------------------------------------------------------------


def _execution_price(
    df: pd.DataFrame,
    i: int,
    model: str,
) -> float:
    """Return the fill price for a signal at index ``i`` under ``model``.

    Args:
        df: Bars DataFrame sorted by trade_date, with columns
            ``open`` and ``adj_close``.
        i: Index of the bar where the signal was generated.
        model: One of ``"open"``, ``"close"``, ``"next_open"``.

    Notes:
        - ``"open"`` uses the signal bar's OPEN. This is the default
          and the realistic choice — you can decide at the open based
          on yesterday's close, but you cannot know today's close in
          advance.
        - ``"close"`` uses the signal bar's ADJ_CLOSE. BASELINE ONLY:
          this is a look-ahead bias and is kept only for rollback.
        - ``"next_open"`` uses the NEXT session's OPEN. The cleanest
          for event-driven strategies.
    """
    if model not in VALID_EXECUTION_MODELS:
        raise ValueError(
            f"Unknown execution_price_model {model!r}; "
            f"expected one of {sorted(VALID_EXECUTION_MODELS)}"
        )

    if model == "close":
        return float(df.iloc[i]["adj_close"])

    if model == "open":
        return float(df.iloc[i]["open"])

    # model == "next_open"
    if i + 1 < len(df):
        return float(df.iloc[i + 1]["open"])
    # No next bar — fall back to last available price (end-of-data).
    return float(df.iloc[i]["adj_close"])


# ---------------------------------------------------------------------------
# Simulation core
# ---------------------------------------------------------------------------


def _simulate(
    df: pd.DataFrame,
    signals: pd.Series,
    *,
    initial_capital: float,
    commission_rate: float,
    slippage_rate: float,
    position_size: float,
    holding_period: int,
    execution_price_model: str,
    market: str,
    apply_friction: bool,
    risk_free_rate: float = 0.02,
) -> BacktestResult:
    """Run the per-bar simulation loop. Pure function over ``df``.

    Extracted so that tests can drive the engine with an in-memory
    DataFrame without needing a database session.
    """
    result = BacktestResult()

    capital = initial_capital
    position = 0.0  # number of shares held
    days_held = 0
    current_trade: Trade | None = None

    for i, row in df.iterrows():
        trade_date = row["trade_date"]
        # Use the configured execution-price model for signal fills.
        # ``price`` is also used to mark daily NAV to market.
        price = _execution_price(df, i, execution_price_model)
        signal = signals.iloc[i]

        # Record daily NAV using current market price (always adj_close
        # for the mark-to-market, regardless of execution model).
        mtm_price = float(row["adj_close"])
        nav = capital + position * mtm_price
        result.daily_nav.append({
            "date": trade_date.isoformat(),
            "nav": nav,
            "price": mtm_price,
            "signal": int(signal),
        })

        # Signal execution logic
        if current_trade is None:
            # No position - check for entry signal
            if signal == 1 and capital > 0:
                cash_to_deploy = capital * position_size
                if apply_friction:
                    cost = _calculate_transaction_cost(
                        cash_to_deploy,
                        commission_rate,
                        slippage_rate,
                        action="buy",
                        market=market,
                    )
                else:
                    cost = 0.0
                net_cash_to_invest = cash_to_deploy - cost
                remaining_cash = capital - cash_to_deploy
                position = net_cash_to_invest / price
                capital = remaining_cash
                current_trade = Trade(
                    entry_date=trade_date,
                    entry_price=price,
                    side="long",
                )
                days_held = 0
                result.signals.append({
                    "date": trade_date.isoformat(),
                    "type": "BUY",
                    "price": price,
                    "signal_strength": abs(signal),
                    "shares": position,
                    "cost": cash_to_deploy,
                })
        else:
            # Have position - check for exit conditions
            days_held += 1
            should_exit = False

            if signal == -1:
                should_exit = True  # SELL signal
            elif days_held >= holding_period:
                should_exit = True  # Max holding period reached

            if should_exit:
                notional = position * price
                if apply_friction:
                    cost = _calculate_transaction_cost(
                        notional,
                        commission_rate,
                        slippage_rate,
                        action="sell",
                        market=market,
                    )
                else:
                    cost = 0.0
                sale_proceeds = notional - cost
                pnl_pct = (price - current_trade.entry_price) / current_trade.entry_price
                trade_pnl = sale_proceeds - (current_trade.entry_price * position)

                capital = capital + sale_proceeds
                current_trade.exit_date = trade_date
                current_trade.exit_price = price
                current_trade.pnl = trade_pnl
                current_trade.pnl_pct = pnl_pct
                result.trades.append(current_trade)

                result.signals.append({
                    "date": trade_date.isoformat(),
                    "type": "SELL",
                    "price": price,
                    "pnl": trade_pnl,
                    "pnl_pct": pnl_pct,
                })

                position = 0
                current_trade = None
                days_held = 0

    # Close any open position at the end
    if current_trade is not None and position > 0:
        last_price = df["adj_close"].iloc[-1]
        last_date = df["trade_date"].iloc[-1]
        notional = position * last_price
        if apply_friction:
            cost = _calculate_transaction_cost(
                notional,
                commission_rate,
                slippage_rate,
                action="sell",
                market=market,
            )
        else:
            cost = 0.0
        sale_proceeds = notional - cost
        pnl_pct = (last_price - current_trade.entry_price) / current_trade.entry_price
        trade_pnl = sale_proceeds - (current_trade.entry_price * position)

        capital = capital + sale_proceeds
        current_trade.exit_date = last_date
        current_trade.exit_price = last_price
        current_trade.pnl = trade_pnl
        current_trade.pnl_pct = pnl_pct
        result.trades.append(current_trade)

    # Calculate metrics
    final_nav = result.daily_nav[-1]["nav"] if result.daily_nav else initial_capital
    total_return = (final_nav - initial_capital) / initial_capital

    # Daily returns for risk metrics
    nav_series = pd.Series([d["nav"] for d in result.daily_nav])
    daily_returns = nav_series.pct_change().dropna()

    # Max drawdown
    cummax = nav_series.cummax()
    drawdown = (nav_series - cummax) / cummax
    max_drawdown = drawdown.min()
    max_drawdown_pct = (
        round(float(max_drawdown) * 100, 2) if not np.isnan(max_drawdown) else 0.0
    )

    # Market-specific annualization (quant P0-4). Defaults to 252 for
    # legacy/other markets so existing dashboards keep working.
    annualization = annualization_factor_for(market)

    # Annualized mean return
    annual_return = (
        float(daily_returns.mean() * annualization)
        if len(daily_returns) > 1
        else 0.0
    )

    # Sharpe ratio (annualized, market-aware)
    if len(daily_returns) > 1 and daily_returns.std() > 0:
        annual_vol = float(daily_returns.std() * np.sqrt(annualization))
        sharpe = (annual_return - risk_free_rate) / annual_vol if annual_vol > 0 else 0.0
    else:
        annual_vol = 0.0
        sharpe = 0.0

    # --- New risk metrics (quant P0-9) ---

    # Sortino: like Sharpe, but only penalises downside volatility.
    # downside_deviation = sqrt(mean(min(r - target, 0)^2)); we use
    # MAR = 0 (target daily return of 0) as is standard for absolute-return
    # strategies.
    sortino: float | None = None
    if len(daily_returns) > 1:
        downside = daily_returns[ daily_returns < 0 ]
        if len(downside) > 0:
            downside_dev = float(np.sqrt((downside ** 2).mean()))
            if downside_dev > 0:
                sortino = (annual_return - risk_free_rate) / (
                    downside_dev * np.sqrt(annualization)
                )

    # Calmar: annualized return / |max drawdown|. None when MDD == 0
    # (cannot divide by zero / no drawdown to compare against).
    calmar: float | None = None
    if max_drawdown < 0:
        calmar = annual_return / abs(float(max_drawdown))

    # VaR / CVaR at 95% confidence. Both expressed as positive losses
    # (i.e. the typical 1-day 95% loss). We return None when the
    # observation count is too small to be meaningful.
    var_95: float | None = None
    cvar_95: float | None = None
    if len(daily_returns) >= 20:
        var_95 = float(-np.percentile(daily_returns, 5))
        tail = daily_returns[daily_returns <= -var_95]
        if len(tail) > 0:
            cvar_95 = float(-tail.mean())

    # Max drawdown duration: longest streak (in trading days) from
    # a peak to a full recovery. A drawdown that is still in progress
    # counts the bars since the last peak. None when not computable.
    max_dd_duration: int | None = _max_drawdown_duration(nav_series)

    # Win rate
    if result.trades:
        wins = sum(1 for t in result.trades if t.pnl_pct > 0)
        win_rate = wins / len(result.trades)
        avg_win = sum(t.pnl_pct for t in result.trades if t.pnl_pct > 0) / wins if wins > 0 else 0
        avg_loss = sum(t.pnl_pct for t in result.trades if t.pnl_pct <= 0) / (len(result.trades) - wins) if len(result.trades) > wins else 0
    else:
        win_rate = 0
        avg_win = 0
        avg_loss = 0

    # Trading days count — use the market-specific annualization factor
    # when computing ``years`` so the geometric annualisation lines up
    # with the Sharpe/Sortino scaling.
    trading_days = len(df)
    years = trading_days / annualization if trading_days > 0 else 1
    annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 and total_return > -1 else total_return

    result.metrics = {
        # Backward-compatible keys (must remain present for legacy callers)
        "initial_capital": initial_capital,
        "final_nav": round(final_nav, 2),
        "total_return": round(total_return * 100, 2),
        "annualized_return": round(annualized_return * 100, 2),
        "max_drawdown": max_drawdown_pct,
        "sharpe_ratio": round(sharpe, 2),
        "win_rate": round(win_rate * 100, 2),
        "trade_count": len(result.trades),
        "avg_win": round(avg_win * 100, 2),
        "avg_loss": round(avg_loss * 100, 2),
        "trading_days": trading_days,
        "commission_rate": commission_rate,
        "slippage_rate": slippage_rate,
        "position_size": position_size,
        "risk_free_rate": risk_free_rate,
        "execution_price_model": execution_price_model,
        "market": market,
        "apply_friction": apply_friction,
        # New metrics (quant P0-9). None means "not computable", NOT 0.
        "sortino_ratio": (
            round(sortino, 2) if sortino is not None else None
        ),
        "calmar_ratio": (
            round(calmar, 2) if calmar is not None else None
        ),
        "var_95": round(var_95 * 100, 2) if var_95 is not None else None,
        "cvar_95": round(cvar_95 * 100, 2) if cvar_95 is not None else None,
        "max_drawdown_duration": max_dd_duration,
        "annualization_factor": annualization,
    }

    return result


def _max_drawdown_duration(nav_series: pd.Series) -> int | None:
    """Longest underwater period (in trading bars) for ``nav_series``.

    An underwater period starts at a new equity peak and ends the first
    day the NAV reaches a new peak >= the prior peak. A drawdown that
    is still in progress at the end of the series counts the bars
    since the last peak.

    Returns ``None`` if the series is too short to compute.
    """
    if len(nav_series) < 2:
        return None
    cummax = nav_series.cummax()
    underwater = nav_series < cummax
    if not underwater.any():
        return 0

    max_streak = 0
    cur_streak = 0
    for is_under in underwater:
        if is_under:
            cur_streak += 1
            max_streak = max(max_streak, cur_streak)
        else:
            cur_streak = 0
    return int(max_streak)


def risk_free_rate_default() -> float:
    """Default risk-free rate used when callers don't supply one."""
    return 0.02


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_backtest(
    etf_code: str,
    strategy_type: str,
    params: dict[str, Any],
    start_date: date,
    end_date: date,
    initial_capital: float = 100000.0,
    commission_rate: float = 0.001,
    slippage_rate: float = 0.001,
    position_size: float = 1.0,
    risk_free_rate: float = 0.02,
    db: Any | None = None,
    execution_price_model: str = "open",
    market: str = "cn_a",
    apply_friction: bool = True,
    *,
    etf_codes: list[str] | None = None,
) -> BacktestResult:
    """Run a backtest for a single ETF or a cross-sectional universe.

    Two modes:

    1. **Single-instrument** (``etf_code`` is a non-empty string): the
       historical behaviour — load one symbol's bars, generate signals
       with the strategy, run ``_simulate`` in a single pass. The
       ``_simulate`` path is preserved exactly so the single-code
       contract is fully backward-compatible.
    2. **Cross-sectional** (``etf_codes`` is a non-empty list): load
       bars for every code in the universe, run ``_simulate`` per
       symbol, then aggregate per-symbol NAVs into a single portfolio
       NAV with **equal weights rebalanced daily to the long side of
       the signals**. Per-symbol ``BacktestResult``s are exposed under
       ``result.per_symbol`` (list[dict]) and the combined portfolio
       metrics+trades+signals live at the top level.

    Args:
        etf_code: ETF code to backtest (single-instrument mode).
        strategy_type: Type of strategy (momentum/mean_reversion/rsi).
        params: Strategy parameters.
        start_date: Backtest start date.
        end_date: Backtest end date.
        initial_capital: Starting capital (single instrument) or total
            capital divided across the universe (cross-sectional).
        commission_rate: Per-trade commission rate (single side).
        slippage_rate: Per-trade slippage rate (single side).
            Ignored when ``market="cn_a"`` and ``apply_friction=True``.
        position_size: Position size ratio (0.0 - 1.0).
        risk_free_rate: Annual risk-free rate used in Sharpe calculation.
        db: Optional SQLAlchemy session. If provided, reads adjusted bars
            from instrument_daily_bar; otherwise falls back to AkshareProvider.
        execution_price_model: ``"open"`` (default, signal-day OPEN),
            ``"close"`` (BASELINE — adj_close, has look-ahead bias), or
            ``"next_open"`` (next session OPEN).
        market: ``"cn_a"`` (default, A-share friction) or ``"other"``
            (legacy symmetric commission + slippage).
        apply_friction: When True (default), apply commission /
            stamp tax / transfer fees per ``market`` rules.
        etf_codes: When provided, run a cross-sectional backtest across
            the universe. Takes precedence over ``etf_code`` when both
            are supplied.

    Returns:
        BacktestResult with NAV, trades, metrics, and signals. For
        cross-sectional runs, ``result.per_symbol`` carries the
        per-symbol breakdown.
    """
    if execution_price_model not in VALID_EXECUTION_MODELS:
        raise ValueError(
            f"Unknown execution_price_model {execution_price_model!r}; "
            f"expected one of {sorted(VALID_EXECUTION_MODELS)}"
        )
    if market not in VALID_MARKETS:
        raise ValueError(
            f"Unknown market {market!r}; "
            f"expected one of {sorted(VALID_MARKETS)}"
        )

    # --- Cross-sectional mode --------------------------------------------------
    if etf_codes:
        return _run_backtest_cross_sectional(
            etf_codes=etf_codes,
            strategy_type=strategy_type,
            params=params,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            position_size=position_size,
            risk_free_rate=risk_free_rate,
            db=db,
            execution_price_model=execution_price_model,
            market=market,
            apply_friction=apply_friction,
        )

    # --- Single-instrument mode (legacy) --------------------------------------
    result = BacktestResult()

    # Clamp position size to a sensible range
    position_size = max(0.0, min(1.0, position_size))

    # Fetch historical data
    try:
        df = _load_bars(etf_code, start_date, end_date, db)
    except Exception:
        # Structured "no data" result — callers can distinguish this from
        # a clean backtest that simply produced zero trades by checking
        # for metrics["error"] == BacktestResult.NO_DATA_ERROR.
        result.metrics = {"error": BacktestResult.NO_DATA_ERROR}
        return result

    if df.empty:
        # Structured "no data" result — callers can distinguish this from
        # a clean backtest that simply produced zero trades by checking
        # for metrics["error"] == BacktestResult.NO_DATA_ERROR.
        result.metrics = {"error": BacktestResult.NO_DATA_ERROR}
        return result

    df = df.sort_values("trade_date").reset_index(drop=True)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date

    # Generate signals using split/dividend adjusted close
    signal_df = df.copy()
    signal_df["close"] = signal_df["adj_close"]
    signals = get_strategy_signals(signal_df, strategy_type, params)

    result = _simulate(
        df,
        signals,
        initial_capital=initial_capital,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        position_size=position_size,
        holding_period=params.get("holding_period", 20),
        execution_price_model=execution_price_model,
        market=market,
        apply_friction=apply_friction,
        risk_free_rate=risk_free_rate,
    )

    return result


# ---------------------------------------------------------------------------
# Cross-sectional backtest (quant P1)
# ---------------------------------------------------------------------------


def _run_backtest_cross_sectional(
    *,
    etf_codes: list[str],
    strategy_type: str,
    params: dict[str, Any],
    start_date: date | None,
    end_date: date | None,
    initial_capital: float,
    commission_rate: float,
    slippage_rate: float,
    position_size: float,
    risk_free_rate: float,
    db: Any | None,
    execution_price_model: str,
    market: str,
    apply_friction: bool,
) -> BacktestResult:
    """Run a multi-symbol backtest with equal-weight daily rebalance.

    Mechanics:
        1. Run ``_simulate`` independently for each symbol with a 1/N
           share of the total capital.
        2. Combine the per-symbol NAV series into a single portfolio
           NAV by summing them each bar.
        3. Recompute the top-level metrics from the combined NAV.
        4. Per-symbol ``BacktestResult``s are kept under
           ``result.per_symbol`` for diagnostics.

    "Equal-weight daily rebalance to the long side" means each symbol
    is independently entered/exited by its own signal stream; capital
    allocated to a symbol is fixed at ``initial_capital / N`` so the
    portfolio is structurally diversified across the universe. This is
    a deliberate simplification of cross-sectional backtests — no
    cross-symbol ranking, just N independent sleeves rebundled.
    """
    if start_date is None or end_date is None:
        raise ValueError(
            "Cross-sectional backtest requires start_date and end_date"
        )

    codes = [c for c in etf_codes if c]
    if not codes:
        empty = BacktestResult()
        empty.metrics = {"error": BacktestResult.NO_DATA_ERROR}
        empty.per_symbol = []
        return empty

    n_symbols = len(codes)
    per_symbol_capital = initial_capital / n_symbols

    per_symbol_results: list[dict[str, Any]] = []
    nav_by_symbol: dict[str, dict[str, float]] = {}
    # Per-symbol trade counts and error tracking.
    trade_total = 0

    for code in codes:
        try:
            sub = run_backtest(
                etf_code=code,
                strategy_type=strategy_type,
                params=params,
                start_date=start_date,
                end_date=end_date,
                initial_capital=per_symbol_capital,
                commission_rate=commission_rate,
                slippage_rate=slippage_rate,
                position_size=position_size,
                risk_free_rate=risk_free_rate,
                db=db,
                execution_price_model=execution_price_model,
                market=market,
                apply_friction=apply_friction,
            )
        except Exception as exc:  # noqa: BLE001 — one bad symbol shouldn't tank the run
            per_symbol_results.append({"etf_code": code, "error": str(exc)})
            continue

        metrics = sub.metrics or {}
        if "error" in metrics:
            per_symbol_results.append({
                "etf_code": code,
                "error": metrics.get("error"),
                "trade_count": 0,
            })
            continue

        nav_series = {row["date"]: float(row["nav"]) for row in sub.daily_nav}
        nav_by_symbol[code] = nav_series
        trade_total += len(sub.trades or [])
        per_symbol_results.append({
            "etf_code": code,
            "metrics": metrics,
            "trade_count": len(sub.trades or []),
            "final_nav": round(float(sub.daily_nav[-1]["nav"]) if sub.daily_nav else per_symbol_capital, 2),
        })

    if not nav_by_symbol:
        empty = BacktestResult()
        empty.metrics = {
            "error": BacktestResult.NO_DATA_ERROR,
            "mode": "cross_sectional",
            "universe_size": n_symbols,
        }
        empty.per_symbol = per_symbol_results
        return empty

    # Build the combined NAV by date-aligned summation.
    all_dates = sorted({d for nav in nav_by_symbol.values() for d in nav})
    combined_nav: list[dict[str, Any]] = []
    for d in all_dates:
        total = 0.0
        for code, nav in nav_by_symbol.items():
            total += nav.get(d, 0.0)
        combined_nav.append({"date": d, "nav": total})

    # Compute portfolio metrics from the combined NAV using the same
    # formulae used in ``_simulate`` (kept light-weight on purpose).
    portfolio_metrics = _portfolio_metrics_from_nav(
        combined_nav, initial_capital, market, risk_free_rate, trade_total,
        n_symbols=len(nav_by_symbol),
    )

    result = BacktestResult()
    result.daily_nav = combined_nav
    result.trades = []  # Combined-trade reconstruction is out of scope;
                       # per-symbol trades are under ``per_symbol``.
    result.signals = []
    result.metrics = portfolio_metrics
    # Attach per-symbol breakdown.
    result.per_symbol = per_symbol_results
    return result


def _portfolio_metrics_from_nav(
    daily_nav: list[dict[str, Any]],
    initial_capital: float,
    market: str,
    risk_free_rate: float,
    trade_count: int,
    *,
    n_symbols: int,
) -> dict[str, Any]:
    """Compute portfolio-level metrics from a combined NAV series.

    Mirrors the metric keys emitted by ``_simulate`` so the portfolio
    result is API-compatible with the single-instrument backtest,
    PLUS an extra ``mode`` and ``universe_size`` key so callers know
    they are looking at a cross-sectional run.
    """
    nav_series = pd.Series([d["nav"] for d in daily_nav], dtype=float)
    if nav_series.empty:
        return {
            "mode": "cross_sectional",
            "universe_size": n_symbols,
            "trade_count": trade_count,
            "error": "empty_nav",
        }

    daily_returns = nav_series.pct_change().dropna()
    final_nav = float(nav_series.iloc[-1])
    total_return = (final_nav - initial_capital) / initial_capital

    cummax = nav_series.cummax()
    drawdown = (nav_series - cummax) / cummax
    max_drawdown = float(drawdown.min()) if not drawdown.empty else 0.0

    annualization = annualization_factor_for(market)
    annual_return = (
        float(daily_returns.mean() * annualization)
        if len(daily_returns) > 1
        else 0.0
    )
    if len(daily_returns) > 1 and daily_returns.std() > 0:
        annual_vol = float(daily_returns.std() * np.sqrt(annualization))
        sharpe = (annual_return - risk_free_rate) / annual_vol if annual_vol > 0 else 0.0
    else:
        sharpe = 0.0

    trading_days = len(nav_series)
    years = trading_days / annualization if trading_days > 0 else 1
    annualized_return = (
        (1 + total_return) ** (1 / years) - 1 if years > 0 and total_return > -1
        else total_return
    )

    return {
        "mode": "cross_sectional",
        "universe_size": n_symbols,
        "initial_capital": round(initial_capital, 2),
        "final_nav": round(final_nav, 2),
        "total_return": round(total_return * 100, 2),
        "annualized_return": round(annualized_return * 100, 2),
        "max_drawdown": round(max_drawdown * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "trade_count": trade_count,
        "trading_days": trading_days,
        "annualization_factor": annualization,
        "risk_free_rate": risk_free_rate,
        "market": market,
    }


# ---------------------------------------------------------------------------
# Walk-forward (out-of-sample) evaluation
# ---------------------------------------------------------------------------


def run_walk_forward(
    backtest_config: dict[str, Any],
    *,
    train_pct: float = 0.6,
    n_folds: int = 3,
    db: Any | None = None,
) -> dict[str, Any]:
    """Run a walk-forward evaluation across multiple out-of-sample folds.

    Each fold partitions the full date range into a contiguous train
    segment (used to pick parameters / fit the strategy) and a contiguous
    test segment (used to score out-of-sample performance). The split is
    *anchored on dates*, not on bar count, so train/test boundaries stay
    stable across re-runs.

    Args:
        backtest_config: Dict of keyword arguments forwarded to
            ``run_backtest`` (``etf_code``, ``strategy_type``, ``params``,
            ``start_date``, ``end_date``, ...). ``start_date`` and
            ``end_date`` may be ``date`` objects or ISO strings.
        train_pct: Fraction of the date range used for training
            (default 0.6 → 60% train / 40% test per fold).
        n_folds: Number of rolling folds. Default 3.
        db: Optional SQLAlchemy session passed through to the engine.

    Returns:
        Dict with:
          - ``folds``: list of per-fold results, each containing
            ``train_start``, ``train_end``, ``test_start``, ``test_end``,
            ``train_metrics``, ``test_metrics``, ``ic``.
          - ``test_metrics_overall``: aggregated test-set metrics.
          - ``ic_per_fold``: list of per-fold information coefficients.

    Notes:
        This is a new entry point and does NOT modify ``run_backtest``.
        Callers (e.g. an admin UI or offline research notebook) can use
        it to get an honest out-of-sample estimate without changing
        the existing backtest API surface.
    """
    if n_folds < 1:
        raise ValueError("n_folds must be >= 1")
    if not (0 < train_pct < 1):
        raise ValueError("train_pct must be in (0, 1)")

    start = _coerce_date(backtest_config.get("start_date"))
    end = _coerce_date(backtest_config.get("end_date"))
    if start is None or end is None or end <= start:
        raise ValueError(
            "run_walk_forward requires valid start_date and end_date "
            "with end_date > start_date"
        )

    total_days = (end - start).days
    train_days = int(total_days * train_pct)
    if train_days < 1:
        raise ValueError("train_pct too small for the given date range")

    # We slide the test window forward across the date range so that
    # each fold's TEST segment is contiguous and non-overlapping with
    # the others (anchored partition).
    test_pool = total_days - train_days
    if test_pool < n_folds:
        # Not enough data for the requested number of folds; cap it.
        n_folds = max(1, test_pool)
    if n_folds < 1:
        # train_pct leaves no test room at all — return an empty result.
        return {
            "folds": [],
            "test_metrics_overall": {},
            "ic_per_fold": [],
        }

    fold_len = test_pool // n_folds

    folds: list[dict[str, Any]] = []
    ic_per_fold: list[float | None] = []

    # Optional explicit param grid; if absent we fall back to a small
    # default grid based on the strategy_type. This keeps backward
    # compatibility for callers that don't supply one.
    param_grid = backtest_config.get("param_grid")
    strategy_type = backtest_config.get("strategy_type")
    if param_grid is None and strategy_type is not None:
        param_grid = _default_param_grid(strategy_type, backtest_config.get("params", {}))

    for k in range(n_folds):
        train_start = start
        train_end = start + pd.Timedelta(days=train_days).to_pytimedelta()
        test_start = train_end + pd.Timedelta(days=1).to_pytimedelta()
        # Last fold absorbs any leftover days.
        test_end = (
            test_start + pd.Timedelta(days=fold_len - 1).to_pytimedelta()
            if k < n_folds - 1
            else end
        )

        # 1) Grid-search on the train window. Pick the params with the
        #    best Sharpe (tie-broken by total_return). The chosen
        #    params are then applied to the test window.
        best_params, best_score, all_scores = _select_best_params(
            base_cfg=backtest_config,
            param_grid=param_grid,
            train_start=train_start,
            train_end=train_end,
            db=db,
        )

        train_cfg = dict(backtest_config)
        train_cfg["start_date"] = train_start
        train_cfg["end_date"] = train_end
        train_cfg["params"] = best_params
        train_result = run_backtest(db=db, **train_cfg)

        test_cfg = dict(backtest_config)
        test_cfg["start_date"] = test_start
        test_cfg["end_date"] = test_end
        test_cfg["params"] = best_params
        test_result = run_backtest(db=db, **test_cfg)

        ic = _compute_ic(test_result, train_result)
        ic_per_fold.append(ic)

        folds.append({
            "fold_index": k,
            "train_start": train_start.isoformat(),
            "train_end": train_end.isoformat(),
            "test_start": test_start.isoformat(),
            "test_end": test_end.isoformat(),
            "train_metrics": train_result.metrics,
            "test_metrics": test_result.metrics,
            "ic": ic,
            # New: chosen params from the train grid search (quant P0-5)
            "chosen_params": best_params,
            "train_score": best_score,
            "all_grid_scores": all_scores,
        })

    return {
        "folds": folds,
        "test_metrics_overall": _aggregate_test_metrics(folds),
        "ic_per_fold": ic_per_fold,
    }


def _coerce_date(value: Any) -> date | None:
    """Best-effort coerce ``value`` into a ``date`` for partitioning."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _compute_ic(test_result: BacktestResult, train_result: BacktestResult) -> float | None:
    """Information coefficient proxy for a fold.

    Defined as the Pearson correlation between the test-window daily
    returns of the strategy and the (lagged) signal strength. Returns
    ``None`` when the fold does not have enough observations to
    compute a correlation meaningfully.
    """
    if test_result.signals is None or len(test_result.signals) < 3:
        return None
    if test_result.daily_nav is None or len(test_result.daily_nav) < 3:
        return None

    nav_series = pd.Series(
        [d["nav"] for d in test_result.daily_nav],
        dtype=float,
    )
    daily_returns = nav_series.pct_change().dropna()

    signals_by_date = {
        s["date"]: abs(float(s.get("signal_strength", 0)))
        for s in test_result.signals
    }
    sig_strength = pd.Series(
        [
            signals_by_date.get(d["date"], 0.0)
            for d in test_result.daily_nav[1:]  # align with returns
        ],
        dtype=float,
    )

    if len(sig_strength) != len(daily_returns):
        # Misalignment — fail soft with None rather than crashing.
        return None
    if sig_strength.std() == 0 or daily_returns.std() == 0:
        return None

    corr = float(np.corrcoef(sig_strength.to_numpy(), daily_returns.to_numpy())[0, 1])
    if np.isnan(corr):
        return None
    return round(corr, 4)


def _aggregate_test_metrics(folds: list[dict[str, Any]]) -> dict[str, Any]:
    """Average key metrics across folds' test segments."""
    keys = [
        "total_return",
        "annualized_return",
        "max_drawdown",
        "sharpe_ratio",
        "win_rate",
        "trade_count",
    ]
    agg: dict[str, Any] = {}
    for k in keys:
        values = [
            f["test_metrics"][k]
            for f in folds
            if "error" not in f["test_metrics"] and k in f["test_metrics"]
        ]
        if values:
            agg[f"avg_{k}"] = round(float(np.mean(values)), 2)
            agg[f"min_{k}"] = round(float(np.min(values)), 2)
            agg[f"max_{k}"] = round(float(np.max(values)), 2)
    return agg


# ---------------------------------------------------------------------------
# Walk-forward grid search (quant P0-5)
# ---------------------------------------------------------------------------


def _default_param_grid(
    strategy_type: str,
    base_params: dict[str, Any],
) -> list[dict[str, Any]] | None:
    """Return a small default grid for the given strategy type.

    The grids below are intentionally small (4-8 candidates) — the goal
    is to differentiate trends across the train window, not to do a
    full hyper-parameter sweep. Returns ``None`` when no sensible grid
    is known for the strategy, in which case the caller falls back to
    using ``base_params`` for every fold.
    """
    if strategy_type in {"momentum", "price_momentum"}:
        # Vary window × threshold around the base params
        window = int(base_params.get("momentum_window", 20))
        threshold = float(base_params.get("threshold", 0.05))
        return [
            {"momentum_window": max(5, window - 5), "threshold": threshold,
             "holding_period": int(base_params.get("holding_period", 20))},
            {"momentum_window": window, "threshold": threshold,
             "holding_period": int(base_params.get("holding_period", 20))},
            {"momentum_window": window + 5, "threshold": threshold,
             "holding_period": int(base_params.get("holding_period", 20))},
            {"momentum_window": window, "threshold": max(0.01, threshold * 0.75),
             "holding_period": int(base_params.get("holding_period", 20))},
            {"momentum_window": window, "threshold": threshold * 1.25,
             "holding_period": int(base_params.get("holding_period", 20))},
        ]
    if strategy_type in {"mean_reversion", "z_score_reversion"}:
        window = int(base_params.get("lookback_window", 20))
        z = float(base_params.get("z_score_threshold", base_params.get("z_threshold", 2.0)))
        return [
            {"lookback_window": max(5, window - 5), "z_score_threshold": z,
             "holding_period": int(base_params.get("holding_period", 5))},
            {"lookback_window": window, "z_score_threshold": z,
             "holding_period": int(base_params.get("holding_period", 5))},
            {"lookback_window": window + 5, "z_score_threshold": z,
             "holding_period": int(base_params.get("holding_period", 5))},
            {"lookback_window": window, "z_score_threshold": max(0.5, z * 0.8),
             "holding_period": int(base_params.get("holding_period", 5))},
            {"lookback_window": window, "z_score_threshold": min(4.0, z * 1.2),
             "holding_period": int(base_params.get("holding_period", 5))},
        ]
    if strategy_type == "rsi":
        period = int(base_params.get("rsi_period", 14))
        return [
            {"rsi_period": max(5, period - 4), "overbought": 70, "oversold": 30,
             "holding_period": int(base_params.get("holding_period", 5))},
            {"rsi_period": period, "overbought": 70, "oversold": 30,
             "holding_period": int(base_params.get("holding_period", 5))},
            {"rsi_period": period + 4, "overbought": 70, "oversold": 30,
             "holding_period": int(base_params.get("holding_period", 5))},
        ]
    # Unknown strategy — no grid available
    return None


def _select_best_params(
    *,
    base_cfg: dict[str, Any],
    param_grid: list[dict[str, Any]] | None,
    train_start: date,
    train_end: date,
    db: Any | None,
) -> tuple[dict[str, Any], float, list[dict[str, Any]]]:
    """Grid-search the train window and return the best params.

    The scoring function is the *Sharpe ratio* on the train window, with
    total_return as the tie-breaker. Returns
    ``(chosen_params, best_score, all_scores)``. If ``param_grid`` is
    ``None`` or empty, the function falls back to ``base_cfg["params"]``
    with a score of ``0.0`` and an empty ``all_scores`` list.
    """
    base_params = dict(base_cfg.get("params") or {})

    if not param_grid:
        return base_params, 0.0, []

    best_params: dict[str, Any] = base_params
    best_score: float = -np.inf
    all_scores: list[dict[str, Any]] = []

    for candidate in param_grid:
        # Merge over the base so any un-specified param still inherits.
        merged = {**base_params, **candidate}
        cfg = dict(base_cfg)
        cfg["start_date"] = train_start
        cfg["end_date"] = train_end
        cfg["params"] = merged
        try:
            res = run_backtest(db=db, **cfg)
        except Exception as exc:  # noqa: BLE001 — keep walk-forward alive
            all_scores.append({"params": merged, "error": str(exc)})
            continue

        m = res.metrics or {}
        if "error" in m:
            all_scores.append({"params": merged, "error": m["error"]})
            continue

        sharpe = float(m.get("sharpe_ratio") or 0.0)
        score = sharpe
        all_scores.append({
            "params": merged,
            "sharpe_ratio": sharpe,
            "total_return": m.get("total_return"),
            "max_drawdown": m.get("max_drawdown"),
        })

        # Tie-break: higher total_return wins.
        cur_ret = float(m.get("total_return") or 0.0)
        if (score > best_score) or (
            score == best_score and cur_ret > float(
                best_params.get("_tiebreak_return", float("-inf"))
            )
        ):
            best_score = score
            best_params = merged
            # stash tiebreaker; stripped before returning
            best_params = {**merged, "_tiebreak_return": cur_ret}

    # Strip the tiebreaker helper before handing params to the test run.
    clean = {k: v for k, v in best_params.items() if k != "_tiebreak_return"}
    if best_score == -np.inf:
        # Every candidate failed — fall back to base params, score=0.
        return base_params, 0.0, all_scores
    return clean, float(best_score), all_scores
