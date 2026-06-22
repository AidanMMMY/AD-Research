"""Risk indicator calculations.

Provides functions for computing risk metrics
(volatility, max drawdown, Sharpe ratio, period returns).
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

    # Period returns: rolling lookback returns
    result["return_1w"] = (
        result["close"]
        .rolling(window=6, min_periods=2)
        .apply(lambda x: calc_return(x, 5), raw=False)
    )
    result["return_1m"] = (
        result["close"]
        .rolling(window=22, min_periods=5)
        .apply(lambda x: calc_return(x, 21), raw=False)
    )
    result["return_3m"] = (
        result["close"]
        .rolling(window=64, min_periods=10)
        .apply(lambda x: calc_return(x, 63), raw=False)
    )
    result["return_6m"] = (
        result["close"]
        .rolling(window=126, min_periods=15)
        .apply(lambda x: calc_return(x, 126), raw=False)
    )
    result["return_1y"] = (
        result["close"]
        .rolling(window=252, min_periods=20)
        .apply(lambda x: calc_return(x, 252), raw=False)
    )

    return result
