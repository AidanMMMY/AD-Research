"""Risk indicator calculations.

Provides functions for computing risk metrics
(volatility, max drawdown, Sharpe ratio, period returns).

## Unit convention (consistent across this module + calculate_risk_indicators)

All risk metrics are returned as **decimals** (0.1648 not 16.48). Callers
that need to display the value as a percentage must multiply by 100 at
the presentation layer only. The ``sharpe`` ratio is dimensionless
and therefore has no scaling applied.

| Function                         | Returns                  | Notes                       |
|----------------------------------|--------------------------|-----------------------------|
| ``calc_volatility``              | decimal (e.g. 0.1648)    | annualised (× sqrt(252))    |
| ``calc_max_drawdown``            | decimal, negative        | no scaling                  |
| ``calc_return``                  | decimal                  | no scaling                  |
| ``calc_sharpe``                  | ratio (dimensionless)    | no scaling (already a ratio)|
| ``calculate_risk_indicators``    | decimals                 | volatility_*, max_drawdown_*, return_* are decimals; sharpe_* is ratio |

This module is the single source of truth for these unit conventions.
The historical V1 behaviour (× 100) was inconsistent with ``sharpe`` and
made cross-column comparisons (e.g. vol vs sharpe) require bespoke
scaling in every caller.
"""

import numpy as np
import pandas as pd


def calc_volatility(returns: pd.Series, window: int = 20) -> float:
    """Calculate annualized volatility from a return series.

    Args:
        returns: Daily return series (as decimals, e.g. 0.01 = 1%).
        window: Lookback window for std calculation.

    Returns:
        Annualized volatility as a decimal (e.g. 0.1648 ≈ 16.48%).
    """
    recent = returns.tail(window)
    if len(recent) < 2:
        return np.nan
    return recent.std() * np.sqrt(252)


def calc_max_drawdown(prices: pd.Series) -> float:
    """Calculate maximum drawdown from a price series.

    Args:
        prices: Price series.

    Returns:
        Maximum drawdown as a decimal negative number
        (e.g. -0.10 ≈ -10%).
    """
    if len(prices) < 2:
        return np.nan
    cummax = prices.cummax()
    drawdown = (prices - cummax) / cummax
    return drawdown.min()


def calc_sharpe(returns: pd.Series, risk_free_rate: float = 0.02) -> float:
    """Calculate annualized Sharpe ratio.

    Args:
        returns: Daily return series (as decimals).
        risk_free_rate: Annual risk-free rate (default 2%).

    Returns:
        Sharpe ratio.
    """
    if len(returns) < 2:
        return np.nan
    annual_return = returns.mean() * 252
    annual_vol = returns.std() * np.sqrt(252)
    if annual_vol == 0 or np.isnan(annual_vol):
        return np.nan
    return (annual_return - risk_free_rate) / annual_vol


def calc_return(prices: pd.Series, window: int) -> float:
    """Calculate period return over a lookback window.

    Args:
        prices: Price series, sorted ascending by date.
        window: Number of periods to look back.

    Returns:
        Period return as a decimal (e.g. 0.05 ≈ 5%).
    """
    if len(prices) < window:
        return np.nan
    return prices.iloc[-1] / prices.iloc[-window] - 1


def calculate_risk_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all risk indicators for a DataFrame of OHLCV data.

    Computes rolling risk metrics for each row based on historical
    data up to that point. The last row contains the most recent
    risk indicators.

    Input DataFrame must contain columns:
        trade_date, open, high, low, close, volume

    Output DataFrame adds columns (all decimals except sharpe_1y):
        volatility_20d, volatility_60d, max_drawdown_1y, sharpe_1y,
        return_1w, return_1m, return_3m, return_6m, return_1y

    Args:
        df: DataFrame with OHLCV bars, sorted by trade_date ascending.

    Returns:
        DataFrame with risk indicator columns appended.
    """
    result = df.copy()

    # Ensure numeric close prices
    result["close"] = pd.to_numeric(result["close"], errors="coerce")

    # Daily returns (kept as a column for downstream use)
    result["daily_return"] = result["close"].pct_change()

    # Rolling calculations using expanding windows where appropriate
    # Volatility: rolling std over fixed windows, annualized
    result["volatility_20d"] = (
        result["close"]
        .pct_change()
        .rolling(window=20, min_periods=5)
        .std()
        * np.sqrt(252)
    )
    result["volatility_60d"] = (
        result["close"]
        .pct_change()
        .rolling(window=60, min_periods=10)
        .std()
        * np.sqrt(252)
    )

    # Max drawdown: rolling 252-day max drawdown
    result["max_drawdown_1y"] = (
        result["close"]
        .rolling(window=252, min_periods=20)
        .apply(lambda x: calc_max_drawdown(x), raw=False)
    )

    # Sharpe ratio: rolling 252-day Sharpe
    result["sharpe_1y"] = (
        result["close"]
        .pct_change()
        .rolling(window=252, min_periods=20)
        .apply(lambda x: calc_sharpe(x), raw=False)
    )

    # Period returns: true N-period lookback returns (decimals).
    # pct_change(periods=N) computes close_t / close_{t-N} - 1, which is the
    # conventional N-day return.  Using this directly removes the previous
    # window/calc_return mismatch that produced one-period-too-short returns.
    result["return_1w"] = result["close"].pct_change(periods=5)
    result["return_1m"] = result["close"].pct_change(periods=21)
    result["return_3m"] = result["close"].pct_change(periods=63)
    result["return_6m"] = result["close"].pct_change(periods=126)
    result["return_1y"] = result["close"].pct_change(periods=252)

    return result
