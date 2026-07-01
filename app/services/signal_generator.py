"""Signal generation compatibility wrapper.

The legacy signal generation logic has been moved to the registry-driven
``app.services.strategy_engine``. This module keeps the old function
signature so existing callers (``SignalService``, scheduler, API) continue
to work without modification.
"""

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.services.strategy_engine import run_strategy_on_instrument

LOOKBACK_BUFFER = 30


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
    """
    return run_strategy_on_instrument(
        db=db,
        etf_code=etf_code,
        strategy_type=strategy_type,
        params=params,
        trade_date=trade_date,
        lookback_days=lookback_days,
    )
