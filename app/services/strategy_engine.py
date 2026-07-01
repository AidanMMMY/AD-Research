"""Strategy execution engine.

Replaces the hard-coded signal_generator.py with a registry-driven engine
that can run any registered strategy on a single instrument or on a universe
of instruments.
"""

from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.data.repositories import price_repository
from app.strategies.base import StrategyRegistry

# Extra calendar days added to the requested lookback when fetching bars,
# to absorb weekends, public holidays, and exchange closures.
LOOKBACK_BUFFER = 30


def _fetch_bars(
    db: Session,
    etf_code: str,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Fetch adjusted daily bars for a single instrument from the local repo."""
    if price_repository.is_before_list_date(db, etf_code, end_date):
        return pd.DataFrame()

    df = price_repository.get_bars(db, etf_code, start_date, end_date, adjusted=True)
    if df.empty:
        return df

    df = df.rename(columns={"close": "raw_close", "adj_close": "close"})
    df["etf_code"] = etf_code

    numeric_cols = ["open", "high", "low", "close", "volume"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.sort_values("trade_date").reset_index(drop=True)


def run_strategy_on_instrument(
    db: Session,
    etf_code: str,
    strategy_type: str,
    params: dict[str, Any],
    trade_date: date,
    lookback_days: int = 120,
) -> list[dict[str, Any]]:
    """Run a single strategy on a single instrument for the latest bar.

    Returns a list containing zero or one signal dict. The signal dict has
    keys: ``type`` (BUY/SELL/HOLD), ``strength`` (0-100), ``metadata``.
    """
    strategy_class = StrategyRegistry.get(strategy_type)
    if strategy_class is None:
        return []

    strategy = strategy_class(params)
    min_needed = strategy.bars_needed()

    start = trade_date - pd.Timedelta(days=lookback_days + LOOKBACK_BUFFER)
    df = _fetch_bars(db, etf_code, start, trade_date)

    if df.empty or len(df) < min_needed:
        return []

    result = strategy.generate(df)
    if result is None:
        return []

    return [{
        "type": result.signal_type,
        "strength": result.strength,
        "metadata": result.metadata,
    }]


def _fetch_universe_bars(
    db: Session,
    etf_codes: list[str],
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Fetch adjusted daily bars for multiple instruments."""
    df = price_repository.get_bars_for_codes(
        db, etf_codes, start_date, end_date, adjusted=True
    )
    if df.empty:
        return df

    df = df.rename(columns={"close": "raw_close", "adj_close": "close"})

    numeric_cols = ["open", "high", "low", "close", "volume"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.sort_values(["etf_code", "trade_date"]).reset_index(drop=True)


def run_strategy_on_universe(
    db: Session,
    etf_codes: list[str],
    strategy_type: str,
    params: dict[str, Any],
    trade_date: date,
    lookback_days: int = 120,
) -> list[dict[str, Any]]:
    """Run a strategy across a universe of instruments.

    For cross-sectional strategies the strategy's ``generate_universe`` method
    is called with multi-instrument data. For time-series strategies the
    strategy is run per instrument.

    Returns a list of signal dicts. Cross-sectional signals already include
    ``etf_code``; time-series signals have it injected here.
    """
    strategy_class = StrategyRegistry.get(strategy_type)
    if strategy_class is None:
        return []

    strategy = strategy_class(params)

    if strategy.family == "cross_sectional" and hasattr(strategy, "generate_universe"):
        start = trade_date - pd.Timedelta(days=lookback_days + LOOKBACK_BUFFER)
        df = _fetch_universe_bars(db, etf_codes, start, trade_date)
        if df.empty:
            return []
        return strategy.generate_universe(df, trade_date)

    all_signals = []
    for code in etf_codes:
        signals = run_strategy_on_instrument(
            db, code, strategy_type, params, trade_date, lookback_days
        )
        for sig in signals:
            sig["etf_code"] = code
            all_signals.append(sig)
    return all_signals
