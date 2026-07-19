"""Market-specific indicator parameters.

Centralises trading-day calendars, annualisation factors, and return-window
lengths so the pandas and SQL indicator paths can adapt per market without
scattering magic numbers.

This module is deliberately lightweight: it contains only static lookup
tables and helpers.  Downstream calculators read from it at call time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Market = Literal["A股", "US", "CRYPTO"]


@dataclass(frozen=True)
class MarketIndicatorConfig:
    """Indicator calculation parameters for a single market."""

    annualization_factor: int
    """Number of trading/periods per year used to annualise volatility and Sharpe.

    * A-share / US equities: 252 trading days/year.
    * Crypto (24/7): 365 calendar days/year.
    """

    return_windows: dict[str, int]
    """Period-return lookbacks in market-native days.

    Keys: return_1w, return_1m, return_3m, return_6m, return_1y.
    Values are period counts (trading days for equities, calendar days for crypto).
    """

    risk_long_window: int
    """Window for 1-year risk metrics (max_drawdown_1y, sharpe_1y)."""

    risk_long_min_periods: int
    """Minimum observations before long-window risk metrics are emitted."""

    ma_windows: tuple[int, ...]
    """Moving-average windows (must match technical.py defaults)."""

    rsi_window: int
    atr_window: int
    bb_window: int


# ---------------------------------------------------------------------------
# Per-market defaults
# ---------------------------------------------------------------------------

_A_SHARE_US_WINDOWS: dict[str, int] = {
    "return_1w": 5,
    "return_1m": 21,
    "return_3m": 63,
    "return_6m": 126,
    "return_1y": 252,
}

_CRYPTO_WINDOWS: dict[str, int] = {
    "return_1w": 7,    # 7 calendar days
    "return_1m": 30,   # 30 calendar days
    "return_3m": 90,   # 90 calendar days
    "return_6m": 180,  # 180 calendar days
    "return_1y": 365,  # 365 calendar days
}

CONFIG: dict[Market, MarketIndicatorConfig] = {
    "A股": MarketIndicatorConfig(
        annualization_factor=252,
        return_windows=_A_SHARE_US_WINDOWS,
        risk_long_window=252,
        risk_long_min_periods=60,
        ma_windows=(5, 10, 20, 60),
        rsi_window=14,
        atr_window=14,
        bb_window=20,
    ),
    "US": MarketIndicatorConfig(
        annualization_factor=252,
        return_windows=_A_SHARE_US_WINDOWS,
        risk_long_window=252,
        risk_long_min_periods=60,
        ma_windows=(5, 10, 20, 60),
        rsi_window=14,
        atr_window=14,
        bb_window=20,
    ),
    "CRYPTO": MarketIndicatorConfig(
        annualization_factor=365,
        return_windows=_CRYPTO_WINDOWS,
        risk_long_window=365,
        risk_long_min_periods=90,
        ma_windows=(7, 14, 30, 90),
        rsi_window=14,
        atr_window=14,
        bb_window=30,
    ),
}


def get_market_config(market: str) -> MarketIndicatorConfig:
    """Return the indicator config for ``market``.

    Falls back to the A-share config for unknown markets so callers never
    crash on an unrecognised value.
    """
    return CONFIG.get(market, CONFIG["A股"])


def normalise_market(market: str | None) -> Market:
    """Normalise a market string to one of the supported config keys."""
    if market == "CRYPTO" or market == "crypto":
        return "CRYPTO"
    if market == "US" or market == "us":
        return "US"
    return "A股"
