"""Technical indicator calculations.

Provides functions for computing common technical indicators
(MA, RSI, MACD, ATR, Bollinger Bands) on OHLCV data.
"""

import numpy as np
import pandas as pd


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
        RSI series (0-100).
    """
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    # Use Wilder's smoothing (exponential moving average with alpha=1/window),
    # which is the standard definition for RSI.
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


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


def calculate_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all technical indicators for a DataFrame of OHLCV data.

    Input DataFrame must contain columns:
        trade_date, open, high, low, close, volume

    Output DataFrame adds columns:
        ma5, ma10, ma20, ma60, rsi14, macd_dif, macd_dea, macd_hist,
        atr14, bb_upper, bb_lower

    Args:
        df: DataFrame with OHLCV bars, sorted by trade_date ascending.

    Returns:
        DataFrame with indicator columns appended.
    """
    result = df.copy()

    # Ensure numeric types
    for col in ["open", "high", "low", "close", "volume"]:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")

    close = result["close"]
    high = result["high"]
    low = result["low"]

    # Moving averages
    result["ma5"] = calc_ma(close, window=5)
    result["ma10"] = calc_ma(close, window=10)
    result["ma20"] = calc_ma(close, window=20)
    result["ma60"] = calc_ma(close, window=60)

    # RSI
    result["rsi14"] = calc_rsi(close, window=14)

    # MACD
    dif, dea, hist = calc_macd(close)
    result["macd_dif"] = dif
    result["macd_dea"] = dea
    result["macd_hist"] = hist

    # ATR
    result["atr14"] = calc_atr(high, low, close, window=14)

    # Bollinger Bands
    bb_upper, bb_lower = calc_bollinger(close)
    result["bb_upper"] = bb_upper
    result["bb_lower"] = bb_lower

    return result
