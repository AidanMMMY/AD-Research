"""Backtest engine core.

Simulates trading based on strategy signals and calculates performance metrics.
"""

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from app.data.indicators.technical import calc_rsi


def _load_bars(etf_code: str, start_date: date, end_date: date, db: Any | None) -> pd.DataFrame:
    """Load historical bars for backtesting.

    If a SQLAlchemy session is provided, read from etf_daily_bar so that
    split/dividend adjusted prices are available. Otherwise fall back to
    AkshareProvider (legacy A-share path).
    """
    if db is not None:
        from sqlalchemy import select
        from app.models.etf import ETFDailyBar

        stmt = (
            select(ETFDailyBar)
            .where(ETFDailyBar.etf_code == etf_code)
            .where(ETFDailyBar.trade_date >= start_date)
            .where(ETFDailyBar.trade_date <= end_date)
            .order_by(ETFDailyBar.trade_date.asc())
        )
        bars = db.execute(stmt).scalars().all()
        if not bars:
            return pd.DataFrame()
        return pd.DataFrame(
            [
                {
                    "trade_date": b.trade_date,
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": float(b.close),
                    "adj_close": float(b.close) * float(b.adj_factor or 1.0),
                    "volume": b.volume,
                }
                for b in bars
            ]
        )

    # Legacy fallback: A-share via Akshare (adjustment info may be unavailable)
    from app.data.providers.akshare_provider import AkshareProvider

    provider = AkshareProvider()
    df = provider.fetch_daily_bars([etf_code], start_date, end_date)
    if df.empty:
        return df
    adj_factor = df.get("adj_factor", pd.Series(1.0, index=df.index)).fillna(1.0)
    df = df.assign(adj_close=df["close"] * adj_factor)
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

    def __init__(self):
        self.daily_nav: list[dict[str, Any]] = []
        self.trades: list[Trade] = []
        self.metrics: dict[str, float] = {}
        self.signals: list[dict[str, Any]] = []


def get_strategy_signals(
    data: pd.DataFrame,
    strategy_type: str,
    params: dict[str, Any],
) -> pd.Series:
    """Generate trading signals based on strategy type.

    Returns a pandas Series with values:
      1 = BUY, -1 = SELL, 0 = HOLD
    """
    signals = pd.Series(0, index=data.index)

    if strategy_type == "momentum":
        window = params.get("momentum_window", 20)
        threshold = params.get("threshold", 0.05)
        momentum = data["close"].pct_change(window)
        signals[momentum > threshold] = 1
        signals[momentum < -threshold] = -1

    elif strategy_type == "mean_reversion":
        window = params.get("lookback_window", 20)
        z_threshold = params.get("z_score_threshold", 2.0)
        ma = data["close"].rolling(window).mean()
        std = data["close"].rolling(window).std()
        z_score = (data["close"] - ma) / std
        signals[z_score < -z_threshold] = 1
        signals[z_score > z_threshold] = -1

    elif strategy_type == "rsi":
        period = params.get("rsi_period", 14)
        overbought = params.get("overbought", 70)
        oversold = params.get("oversold", 30)
        rsi = calc_rsi(data["close"], window=period)
        signals[rsi < oversold] = 1
        signals[rsi > overbought] = -1

    return signals


def _apply_transaction_costs(price: float, commission_rate: float, slippage_rate: float) -> float:
    """Return the effective price after commission and slippage.

    Costs are applied symmetrically: entering at a slightly higher price and
    exiting at a slightly lower price (both reduced by total cost).
    """
    total_cost = commission_rate + slippage_rate
    return price * (1 - total_cost)


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
) -> BacktestResult:
    """Run a backtest for a single ETF with a strategy.

    Args:
        etf_code: ETF code to backtest.
        strategy_type: Type of strategy (momentum/mean_reversion/rsi).
        params: Strategy parameters.
        start_date: Backtest start date.
        end_date: Backtest end date.
        initial_capital: Starting capital.
        commission_rate: Per-trade commission rate (single side).
        slippage_rate: Per-trade slippage rate (single side).
        position_size: Position size ratio (0.0 - 1.0).
        risk_free_rate: Annual risk-free rate used in Sharpe calculation.
        db: Optional SQLAlchemy session. If provided, reads adjusted bars
            from etf_daily_bar; otherwise falls back to AkshareProvider.

    Returns:
        BacktestResult with NAV, trades, metrics, and signals.
    """
    result = BacktestResult()

    # Clamp position size to a sensible range
    position_size = max(0.0, min(1.0, position_size))

    # Fetch historical data
    try:
        df = _load_bars(etf_code, start_date, end_date, db)
    except Exception:
        return result

    if df.empty:
        return result

    df = df.sort_values("trade_date").reset_index(drop=True)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date

    # Generate signals using split/dividend adjusted close
    signal_df = df.copy()
    signal_df["close"] = signal_df["adj_close"]
    signals = get_strategy_signals(signal_df, strategy_type, params)

    # Simulation
    capital = initial_capital
    position = 0.0  # number of shares held
    holding_period = params.get("holding_period", 20)
    days_held = 0
    current_trade: Trade | None = None

    for i, row in df.iterrows():
        trade_date = row["trade_date"]
        price = row["close"]  # execution uses real (unadjusted) close
        signal = signals.iloc[i]

        # Record daily NAV using current market price
        nav = capital + position * price
        result.daily_nav.append({
            "date": trade_date.isoformat(),
            "nav": nav,
            "price": price,
            "signal": int(signal),
        })

        # Signal execution logic
        if current_trade is None:
            # No position - check for entry signal
            if signal == 1 and capital > 0:
                # BUY: deploy only position_size of available cash
                cash_to_deploy = capital * position_size
                remaining_cash = capital - cash_to_deploy
                effective_price = _apply_transaction_costs(price, commission_rate, slippage_rate)
                position = cash_to_deploy / effective_price
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
                # SELL: close position at effective price
                effective_price = _apply_transaction_costs(price, commission_rate, slippage_rate)
                sale_proceeds = position * effective_price
                pnl_pct = (effective_price - current_trade.entry_price) / current_trade.entry_price
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
        last_price = df["close"].iloc[-1]
        last_date = df["trade_date"].iloc[-1]
        effective_price = _apply_transaction_costs(last_price, commission_rate, slippage_rate)
        sale_proceeds = position * effective_price
        pnl_pct = (effective_price - current_trade.entry_price) / current_trade.entry_price
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

    # Sharpe ratio (annualized)
    if len(daily_returns) > 1 and daily_returns.std() > 0:
        annual_return = daily_returns.mean() * 252
        annual_vol = daily_returns.std() * np.sqrt(252)
        sharpe = (annual_return - risk_free_rate) / annual_vol
    else:
        sharpe = 0

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

    # Trading days count
    trading_days = len(df)
    years = trading_days / 252 if trading_days > 0 else 1
    annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 and total_return > -1 else total_return

    result.metrics = {
        "initial_capital": initial_capital,
        "final_nav": round(final_nav, 2),
        "total_return": round(total_return * 100, 2),
        "annualized_return": round(annualized_return * 100, 2),
        "max_drawdown": round(max_drawdown * 100, 2),
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
    }

    return result
