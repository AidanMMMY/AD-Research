"""Signal generation compatibility wrapper.

The legacy signal generation logic has been moved to the registry-driven
``app.services.strategy_engine``. This module keeps the old function
signatures so existing callers (``SignalService``, scheduler, API, tests)
continue to work without modification.
"""

from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.services.strategy_engine import _fetch_bars, run_strategy_on_instrument

LOOKBACK_BUFFER = 30


def _fetch_bars_from_db(
    db: Session,
    etf_code: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    """Backwards-compatible alias for ``strategy_engine._fetch_bars``.

    Returns a DataFrame with at least the ``close`` and ``etf_code`` columns
    for the inclusive ``[start, end]`` window. Empty when the window is
    pre-listing or no bars exist.
    """
    return _fetch_bars(db, etf_code, start, end)


def generate_signals_for_strategy(
    db: Session,
    etf_code: str,
    strategy_type: str,
    params: dict[str, Any],
    trade_date: date,
    lookback_days: int = 60,
) -> list[dict[str, Any]]:
    """Generate signals for a single strategy on a single ETF.

    DEPRECATED: Use ``app.services.strategy_engine.run_strategy_on_instrument``
    directly in new code.

    The effective lookback passed to the engine is the user-supplied
    ``lookback_days`` plus ``LOOKBACK_BUFFER`` (calendar days), so the
    strategy has enough bar history to absorb weekends and exchange
    holidays. The constant is intentionally named, not a magic number.
    """
    effective_lookback = lookback_days + LOOKBACK_BUFFER
    return run_strategy_on_instrument(
        db=db,
        etf_code=etf_code,
        strategy_type=strategy_type,
        params=params,
        trade_date=trade_date,
        lookback_days=effective_lookback,
    )
