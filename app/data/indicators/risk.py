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

from app.data.indicators.market_config import get_market_config


# Minimum number of observations required before the long-window risk
# metrics (``sharpe_1y`` / ``max_drawdown_1y``) are considered trustworthy.
# 60 ≈ one trading quarter — short enough to react to new listings, long
# enough that the 252-day rolling window has enough valid samples to
# produce a meaningful number instead of an over-fitted one.
RISK_LONG_MIN_PERIODS = 60


def ensure_min_sample(
    series: pd.Series,
    min_periods: int,
    days_since_listing: int | None,
) -> pd.Series:
    """Mask a rolling risk series when the sample is too small.

    Returns a series of the same length / index as ``series``. When
    ``days_since_listing`` is ``None`` (i.e. the upstream inventory has no
    ``list_date``), the series is passed through unchanged — the upstream
    rolling ``min_periods`` gate is the single source of truth so the
    pandas and SQL thresholds align.

    When ``days_since_listing`` is known and less than ``min_periods``,
    the entire series is blanket-masked with ``NaN``. Otherwise, rows
    where fewer than ``min_periods`` of the most recent observations are
    non-null are replaced with ``NaN``.
    """
    out = series.copy()

    if days_since_listing is None:
        return out

    # Rule (a): listed for less than the window → blanket-mask the series.
    if days_since_listing < min_periods:
        return pd.Series([np.nan] * len(series), index=series.index)

    # Rule (b): rolling not-null count must clear the bar.
    notnull_count = series.notna().rolling(min_periods, min_periods=min_periods).sum()
    out = out.where(notnull_count >= min_periods)

    return out


def calc_volatility(
    returns: pd.Series,
    window: int = 20,
    *,
    annualization_factor: int = 252,
) -> float:
    """Calculate annualized volatility from a return series.

    Args:
        returns: Daily return series (as decimals, e.g. 0.01 = 1%).
        window: Lookback window for std calculation.
        annualization_factor: Periods per year used for annualisation
            (252 for A-share/US equities, 365 for crypto).

    Returns:
        Annualized volatility as a decimal (e.g. 0.1648 ≈ 16.48%).
    """
    recent = returns.tail(window)
    if len(recent) < 2:
        return np.nan
    return recent.std() * np.sqrt(annualization_factor)


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


def calc_sharpe(
    returns: pd.Series,
    risk_free_rate: float = 0.02,
    *,
    annualization_factor: int = 252,
    trading_days_per_year: int = 252,
) -> float:
    """Calculate annualized Sharpe ratio.

    Args:
        returns: Daily return series (as decimals).
        risk_free_rate: Annual risk-free rate (default 2%).
        annualization_factor: Periods per year used to annualise the
            standard deviation (252 for equities, 365 for crypto).
        trading_days_per_year: Periods per year used to annualise the
            mean return. Usually equals ``annualization_factor``.

    Returns:
        Sharpe ratio.
    """
    if len(returns) < 2:
        return np.nan
    annual_return = returns.mean() * trading_days_per_year
    annual_vol = returns.std() * np.sqrt(annualization_factor)
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


# Mapping from period label to A-share/US trading-day lookback window.
# Centralised so the same windows are used by legacy callers and by the
# default A-share ``calculate_return_indicators`` path.  Crypto and other
# markets receive their windows from ``MarketIndicatorConfig.return_windows``.
RETURN_PERIODS: dict[str, int] = {
    "return_1w": 5,
    "return_1m": 21,
    "return_3m": 63,
    "return_6m": 126,
    "return_1y": 252,
}


def calculate_return_indicators(
    df: pd.DataFrame,
    *,
    market: str = "A股",
    config: object | None = None,
) -> pd.DataFrame:
    """Calculate period returns (1w/1m/3m/6m/1y) on the ``close`` column.

    This is intentionally a separate function from
    :func:`calculate_risk_indicators` so callers can choose which
    price column to feed in. In particular the platform calls this on
    the **raw** market close (giving the "price-return" view that the
    UI exposes for ETFs), while volatility / drawdown / Sharpe are
    still computed on the dividend-adjusted close for cross-time
    comparability.

    Input DataFrame must contain a ``close`` column sorted ascending.
    Output DataFrame adds ``return_1w``, ``return_1m``, ``return_3m``,
    ``return_6m``, ``return_1y`` (all decimals, e.g. 0.05 = 5%).

    Args:
        df: DataFrame with at least a ``close`` column.
        market: Market key used to look up windows when ``config`` is
            not provided.
        config: Optional ``MarketIndicatorConfig`` overriding the
            market lookup.

    Returns:
        DataFrame with the period return columns appended.
    """
    if config is None:
        config = get_market_config(market)

    result = df.copy()
    close = pd.to_numeric(result["close"], errors="coerce")
    for col, periods in config.return_windows.items():
        result[col] = close.pct_change(periods=periods)
    return result


def calculate_risk_indicators(
    df: pd.DataFrame,
    days_since_listing: int | None = None,
    *,
    market: str = "A股",
    config: object | None = None,
) -> pd.DataFrame:
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
        days_since_listing: Optional integer — number of market-native
            days since the instrument was listed. When provided, the
            long-window metrics (``sharpe_1y`` / ``max_drawdown_1y``)
            are blanked out for instruments listed less than the
            configured ``risk_long_min_periods`` (see
            :func:`ensure_min_sample`). When ``None``, only the
            rolling-not-null gate is applied — this preserves backwards
            compatibility for callers that haven't migrated to passing
            ``list_date``.
        market: Market key used to load the correct windows and
            annualisation factor when ``config`` is not provided.
        config: Optional ``MarketIndicatorConfig`` overriding the
            market lookup.

    Returns:
        DataFrame with risk indicator columns appended.
    """
    if config is None:
        config = get_market_config(market)

    result = df.copy()

    # Ensure numeric close prices
    result["close"] = pd.to_numeric(result["close"], errors="coerce")

    # Daily returns (kept as a column for downstream use)
    result["daily_return"] = result["close"].pct_change()

    ann_factor = np.sqrt(config.annualization_factor)

    # Volatility: rolling std over fixed windows, annualized. Short
    # windows (20d / 60d) keep their existing min_periods — they are
    # by design short-window indicators.
    result["volatility_20d"] = (
        result["close"]
        .pct_change()
        .rolling(window=20, min_periods=5)
        .std()
        * ann_factor
    )
    result["volatility_60d"] = (
        result["close"]
        .pct_change()
        .rolling(window=60, min_periods=10)
        .std()
        * ann_factor
    )

    long_window = config.risk_long_window
    long_min_periods = config.risk_long_min_periods

    # Max drawdown: rolling long-window max drawdown. ``min_periods``
    # comes from the market config so newly-listed instruments don't emit
    # unstable drawdown estimates. The ``ensure_min_sample`` blanket mask
    # only applies when ``days_since_listing`` is known and shorter than
    # the window; otherwise we rely on the rolling min_periods gate, which
    # matches the SQL path threshold.
    raw_max_dd = (
        result["close"]
        .rolling(window=long_window, min_periods=long_min_periods)
        .apply(lambda x: calc_max_drawdown(x), raw=False)
    )
    result["max_drawdown_1y"] = (
        ensure_min_sample(raw_max_dd, long_min_periods, days_since_listing)
        if days_since_listing is not None
        else raw_max_dd
    )

    # Sharpe ratio: rolling long-window Sharpe. Same tightening rationale
    # as max_drawdown_1y — ``min_periods`` comes from the market config.
    raw_sharpe = (
        result["close"]
        .pct_change()
        .rolling(window=long_window, min_periods=long_min_periods)
        .apply(
            lambda x: calc_sharpe(
                x,
                annualization_factor=config.annualization_factor,
                trading_days_per_year=config.annualization_factor,
            ),
            raw=False,
        )
    )
    result["sharpe_1y"] = (
        ensure_min_sample(raw_sharpe, long_min_periods, days_since_listing)
        if days_since_listing is not None
        else raw_sharpe
    )

    # Period returns: true N-period lookback returns (decimals).
    # pct_change(periods=N) computes close_t / close_{t-N} - 1, which is the
    # conventional N-day return.  Using this directly removes the previous
    # window/calc_return mismatch that produced one-period-too-short returns.
    # NOTE: the platform's main entrypoint (``calculate_single_etf`` in
    # calculator.py) overrides these with returns via
    # :func:`calculate_return_indicators`, because adjusted-close returns
    # bake future dividends into the divisor and report "total return"
    # semantics — which makes the 1m/3m/1y numbers shown on the ETF
    # detail page look unrealistically small whenever a dividend lands
    # inside the lookback window. See calculator.py for the override.
    for col, periods in config.return_windows.items():
        result[col] = result["close"].pct_change(periods=periods)

    return result
