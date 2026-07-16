"""Celery tasks for indicator calculation.

These tasks offload CPU/DB-heavy indicator recalculation from the backend
container to dedicated celery workers.
"""

from datetime import date

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.data.indicators.calculator import batch_calculate_indicators


def _parse_date(value: date | str | None) -> date | None:
    """Accept either a date object or an ISO date string."""
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, queue="indicator")
def calculate_indicators(
    self,
    target_date: date | str | None = None,
    full_history: bool = False,
    market_filter: str = "A股",
    instrument_type_filter: str | None = None,
    code_prefix: str | list[str] | None = None,
) -> int:
    """Calculate technical/risk indicators for all active instruments in a market.

    Args:
        target_date: Only compute indicators up to and including this date.
            Accepts ``datetime.date`` or ISO string ``"YYYY-MM-DD"``.
        full_history: If True, compute every historical trade date instead of
            only the latest day.
        market_filter: Market to filter by, e.g. ``"A股"``, ``"US"``,
            ``"CRYPTO"``.
        instrument_type_filter: Optional secondary filter on
            ``etf_info.instrument_type`` — pass ``"ETF"`` or ``"STOCK"`` to
            narrow the universe. Defaults to ``None`` which keeps the
            original behaviour where ``market_filter='A股'`` already covers
            every active A-share code in a single pass.
        code_prefix: Optional prefix filter on ``etf_info.code``. Used to
            shard a large universe (e.g. A-share stocks) across multiple
            workers without code duplication.

    Returns:
        Number of indicator records written.
    """
    effective_date = _parse_date(target_date)
    db = SessionLocal()
    try:
        count = batch_calculate_indicators(
            db,
            target_date=effective_date,
            full_history=full_history,
            market_filter=market_filter,
            instrument_type_filter=instrument_type_filter,
            code_prefix=code_prefix,
        )
        return count
    except Exception as exc:
        # Retry on transient DB/lock errors; permanent errors will raise after
        # max_retries.
        raise self.retry(exc=exc)
    finally:
        db.close()
