"""Risk indicator calculations.

Provides functions for computing risk metrics
(volatility, max drawdown, Sharpe ratio, period returns).

## Unit convention (consistent across this module + calculate_risk_indicators)

| Function                         | Returns                  | Notes                    |
|----------------------------------|--------------------------|--------------------------|
| ``calc_volatility``              | percentage (e.g. 16.48)  | × 100 (annualised)       |
| ``calc_max_drawdown``            | percentage, negative     | × 100                    |
| ``calc_return``                  | percentage               | × 100                    |
| ``calc_sharpe``                  | ratio (dimensionless)     | no scaling (already a ratio) |
| ``calculate_risk_indicators``    | mixed (see columns)      | volatility_*, max_drawdown_*, return_* are %; sharpe_* is ratio |

PITFALL: callers comparing across columns MUST be aware that
``volatility_20d`` is "16.48" while ``sharpe_1y`` is "1.5" (no × 100).
Future refactor (Sprint N+1) should standardise all outputs to
decimal form (0.1648) for consistency with the rest of the platform.
"""

import numpy as np
import pandas as pd


def calc_volatility(returns: pd.Series, window: int = 20) -> float:
    """Calculate annualized volatility from a return series.

    Args:
        returns: Daily return series (as decimals, e.g. 0.01 = 1%).
        window: Lookback window for std calculation.

    Returns:
        Annualized volatility as a percentage.
    """
    recent = returns.tail(window)
    if len(recent) < 2:
        return np.nan
    return recent.std() * np.sqrt(252) * 100


def calc_max_drawdown(prices: pd.Series) -> float:
    """Calculate maximum drawdown from a price series.

    Args:
        prices: Price series.

    Returns:
        Maximum drawdown as a percentage (negative number).
    """
    if len(prices) < 2:
        return np.nan
    cummax = prices.cummax()
    drawdown = (prices - cummax) / cummax
    return drawdown.min() * 100


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
        Period return as a percentage.
    """
    if len(prices) < window:
        return np.nan
    return (prices.iloc[-1] / prices.iloc[-window] - 1) * 100


def calculate_risk_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all risk indicators for a DataFrame of OHLCV data.

    Computes rolling risk metrics for each row based on historical
    data up to that point. The last row contains the most recent
    risk indicators.

    Input DataFrame must contain columns:
        trade_date, open, high, low, close, volume

    Output DataFrame adds columns:
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
    # Volatility: rolling std over fixed windows
    result["volatility_20d"] = (
        result["close"]
        .pct_change()
        .rolling(window=20, min_periods=5)
        .std()
        * np.sqrt(252)
        * 100
    )
    result["volatility_60d"] = (
        result["close"]
        .pct_change()
        .rolling(window=60, min_periods=10)
        .std()
        * np.sqrt(252)
        * 100
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

    # Period returns: true N-period lookback returns.
    # pct_change(periods=N) computes close_t / close_{t-N} - 1, which is the
    # conventional N-day return.  Using this directly removes the previous
    # window/calc_return mismatch that produced one-period-too-short returns.
    result["return_1w"] = result["close"].pct_change(periods=5) * 100
    result["return_1m"] = result["close"].pct_change(periods=21) * 100
    result["return_3m"] = result["close"].pct_change(periods=63) * 100
    result["return_6m"] = result["close"].pct_change(periods=126) * 100
    result["return_1y"] = result["close"].pct_change(periods=252) * 100

    return result
