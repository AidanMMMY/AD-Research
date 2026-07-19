"""Technical indicator calculations.

Provides functions for computing common technical indicators
(MA, RSI, MACD, ATR, Bollinger Bands) on OHLCV data.
"""

import numpy as np
import pandas as pd

from app.data.indicators.market_config import get_market_config


def calc_ma(series: pd.Series, window: int) -> pd.Series:
    """Calculate simple moving average.

    Args:
        series: Price series.
        window: Rolling window size.

    Returns:
        SMA series.
    """
    return series.rolling(window=window, min_periods=1).mean()


def calc_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """Calculate Relative Strength Index (RSI).

    Args:
        series: Price series (typically close prices).
        window: RSI lookback window (default 14).

    Returns:
        RSI series (0-100). On a perfectly rising series (avg_loss == 0),
        returns 100 (extreme overbought). On a perfectly falling series
        (avg_gain == 0), returns 0. NaN only before the first window samples.
    """
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    # Use Wilder's smoothing (exponential moving average with alpha=1/window),
    # which is the standard definition for RSI.
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    # Treat avg_loss == 0 (perfectly rising) as RS = +inf → RSI = 100
    # Treat avg_gain == 0 (perfectly falling) as RS = 0 → RSI = 0
    # Avoid division-by-zero that would otherwise propagate NaN forever
    # (the previous replace(0, NaN) caused RSI to never trigger SELL on
    # monotonic uptrends, which is the exact opposite of what RSI is for).
    rs = avg_gain / avg_loss.where(avg_loss > 0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.where(avg_loss > 0, 100.0)  # perfectly rising → 100
    rsi = rsi.where(avg_gain > 0, 0.0)    # perfectly falling → 0
    return rsi


def calc_macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate MACD indicator.

    Args:
        series: Price series.
        fast: Fast EMA span.
        slow: Slow EMA span.
        signal: Signal EMA span.

    Returns:
        Tuple of (DIF, DEA, histogram).
    """
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = dif - dea
    return dif, dea, hist


def calc_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14
) -> pd.Series:
    """Calculate Average True Range (ATR) using Wilder smoothing.

    This matches the classic ATR definition used by TradingView, Bloomberg,
    and most charting packages: the first value is the simple mean of the
    first ``window`` true ranges, and subsequent values are smoothed with
    ``alpha = 1 / window``.

    Args:
        high: High price series.
        low: Low price series.
        close: Close price series.
        window: ATR lookback window (default 14).

    Returns:
        ATR series.
    """
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def calc_bollinger(
    series: pd.Series, window: int = 20, num_std: float = 2.0
) -> tuple[pd.Series, pd.Series]:
    """Calculate Bollinger Bands.

    Args:
        series: Price series.
        window: Moving average window (default 20).
        num_std: Number of standard deviations (default 2.0).

    Returns:
        Tuple of (upper band, lower band).
    """
    ma = series.rolling(window=window, min_periods=1).mean()
    std = series.rolling(window=window, min_periods=1).std()
    upper = ma + num_std * std
    lower = ma - num_std * std
    return upper, lower


def calculate_technical_indicators(
    df: pd.DataFrame,
    *,
    market: str = "A股",
    config: object | None = None,
) -> pd.DataFrame:
    """Calculate all technical indicators for a DataFrame of OHLCV data.

    Input DataFrame must contain columns:
        trade_date, open, high, low, close, volume

    Output DataFrame adds columns:
        ma5, ma10, ma20, ma60, rsi14, macd_dif, macd_dea, macd_hist,
        atr14, bb_upper, bb_lower

    Args:
        df: DataFrame with OHLCV bars, sorted by trade_date ascending.
        market: Market key used to load the correct windows when
            ``config`` is not provided.
        config: Optional ``MarketIndicatorConfig`` overriding the
            market lookup.

    Returns:
        DataFrame with indicator columns appended.
    """
    if config is None:
        config = get_market_config(market)

    result = df.copy()

    # Ensure numeric types
    for col in ["open", "high", "low", "close", "volume"]:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")

    close = result["close"]
    high = result["high"]
    low = result["low"]

    ma_windows = config.ma_windows
    # Moving averages: the output column names (ma5/ma10/ma20/ma60) are
    # fixed by the ETFIndicator schema, but the lookback windows are read
    # from the market config so crypto can use 7/14/30/90 calendar days.
    ma_labels = ("ma5", "ma10", "ma20", "ma60")
    for label, window in zip(ma_labels, ma_windows):
        result[label] = calc_ma(close, window=window)

    # RSI
    result["rsi14"] = calc_rsi(close, window=config.rsi_window)

    # MACD
    dif, dea, hist = calc_macd(close)
    result["macd_dif"] = dif
    result["macd_dea"] = dea
    result["macd_hist"] = hist

    # ATR
    result["atr14"] = calc_atr(high, low, close, window=config.atr_window)

    # Bollinger Bands
    bb_upper, bb_lower = calc_bollinger(close, window=config.bb_window)
    result["bb_upper"] = bb_upper
    result["bb_lower"] = bb_lower

    return result
