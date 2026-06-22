"""Chinese A-share trading calendar utilities.

Uses akshare's bundled calendar.json (all trading days from 1990 onward) to
determine whether a date is a trading day, enumerate trading days in a range,
and get the last N trading days. Falls back to weekday-only logic if the
calendar file is unavailable.
"""

from datetime import date, timedelta
from pathlib import Path

import akshare as ak


def _load_trading_dates() -> set[date]:
    """Load A-share trading dates from akshare's bundled calendar file."""
    calendar_path = Path(ak.__file__).parent / "file_fold" / "calendar.json"
    if not calendar_path.exists():
        return set()

    try:
        import json

        with calendar_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        return {date(int(d[:4]), int(d[4:6]), int(d[6:8])) for d in raw}
    except Exception:
        return set()


_TRADING_DATES: set[date] = _load_trading_dates()


def is_trading_day(d: date) -> bool:
    """Return True if ``d`` is an A-share trading day.

    Falls back to ``d.weekday() < 5`` when the calendar file is unavailable.
    """
    if _TRADING_DATES:
        return d in _TRADING_DATES
    return d.weekday() < 5


def get_trading_dates(start: date, end: date) -> list[date]:
    """Return sorted list of trading days in the inclusive range [start, end]."""
    if start > end:
        return []

    if _TRADING_DATES:
        return sorted(d for d in _TRADING_DATES if start <= d <= end)

    # Fallback: weekdays only
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def last_n_trading_days(n: int, anchor: date | None = None) -> list[date]:
    """Return the most recent ``n`` trading days up to and including ``anchor``.

    If ``anchor`` is not provided, uses today.
    """
    if n <= 0:
        return []

    anchor = anchor or date.today()

    if _TRADING_DATES:
        candidates = sorted(d for d in _TRADING_DATES if d <= anchor)
        return candidates[-n:]

    # Fallback: weekdays only
    days = []
    current = anchor
    while len(days) < n:
        if current.weekday() < 5:
            days.append(current)
        current -= timedelta(days=1)
    return sorted(days)


def next_trading_day(anchor: date | None = None) -> date | None:
    """Return the first trading day strictly after ``anchor``.

    Returns ``None`` if the bundled calendar does not extend far enough.
    """
    anchor = anchor or date.today()
    if not _TRADING_DATES:
        return None

    future = sorted(d for d in _TRADING_DATES if d > anchor)
    return future[0] if future else None


def previous_trading_day(anchor: date | None = None) -> date | None:
    """Return the most recent trading day strictly before ``anchor``."""
    anchor = anchor or date.today()
    if not _TRADING_DATES:
        return None

    past = sorted(d for d in _TRADING_DATES if d < anchor)
    return past[-1] if past else None
