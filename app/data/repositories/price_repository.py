"""Centralized price data repository.

All internal consumers of daily OHLCV bars should go through this module
instead of issuing ad-hoc SQLAlchemy queries or calling external providers.
"""

from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.etf import ETFInfo, InstrumentDailyBar


def _compute_adj_close(df: pd.DataFrame) -> pd.DataFrame:
    """Add an adj_close column from close * adj_factor."""
    if df.empty:
        df["adj_close"] = pd.Series(dtype=float)
        return df
    adj_factor = df.get("adj_factor")
    if adj_factor is not None:
        df["adj_close"] = df["close"] * adj_factor.fillna(1.0)
    else:
        df["adj_close"] = df["close"].copy()
    return df


def _bars_to_dataframe(bars: list[InstrumentDailyBar], adjusted: bool) -> pd.DataFrame:
    """Convert ORM rows to a standard DataFrame."""
    if not bars:
        columns = [
            "trade_date", "open", "high", "low", "close", "volume",
            "amount", "change_pct", "turnover_rate", "adj_factor",
        ]
        if adjusted:
            columns.append("adj_close")
        return pd.DataFrame(columns=columns)

    records: list[dict[str, Any]] = []
    for bar in bars:
        records.append(
            {
                "trade_date": bar.trade_date,
                "open": float(bar.open) if bar.open is not None else None,
                "high": float(bar.high) if bar.high is not None else None,
                "low": float(bar.low) if bar.low is not None else None,
                "close": float(bar.close) if bar.close is not None else None,
                "volume": float(bar.volume) if bar.volume is not None else None,
                "amount": float(bar.amount) if bar.amount is not None else None,
                "change_pct": float(bar.change_pct) if bar.change_pct is not None else None,
                "turnover_rate": float(bar.turnover_rate) if bar.turnover_rate is not None else None,
                "adj_factor": float(bar.adj_factor) if bar.adj_factor is not None else 1.0,
            }
        )
    df = pd.DataFrame(records)
    df = df.sort_values("trade_date").reset_index(drop=True)
    df = _compute_adj_close(df)
    if not adjusted:
        df = df.drop(columns=["adj_close"], errors="ignore")
    return df


def get_bars(
    db: Session,
    code: str,
    start_date: date | None = None,
    end_date: date | None = None,
    *,
    adjusted: bool = False,
    limit: int | None = None,
) -> pd.DataFrame:
    """Fetch daily bars for a single instrument from the local database.

    Args:
        db: SQLAlchemy session.
        code: Instrument code (e.g. ``000001.SZ`` or ``AAPL.US``).
        start_date: Inclusive start date. Defaults to the first available bar.
        end_date: Inclusive end date. Defaults to today.
        adjusted: If True, include an ``adj_close`` column computed as
            ``close * adj_factor``.
        limit: If provided, return at most the most recent ``limit`` bars
            within the date range (or overall if no dates are given).

    Returns:
        DataFrame sorted by ``trade_date`` ascending.
    """
    if limit is not None and start_date is None and end_date is None:
        # Most recent N bars
        stmt = (
            select(InstrumentDailyBar)
            .where(InstrumentDailyBar.etf_code == code)
            .order_by(InstrumentDailyBar.trade_date.desc())
            .limit(limit)
        )
        bars = list(db.scalars(stmt).all())
        bars.sort(key=lambda b: b.trade_date)
        return _bars_to_dataframe(bars, adjusted=adjusted)

    stmt = (
        select(InstrumentDailyBar)
        .where(InstrumentDailyBar.etf_code == code)
        .order_by(InstrumentDailyBar.trade_date.asc())
    )
    if start_date is not None:
        stmt = stmt.where(InstrumentDailyBar.trade_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(InstrumentDailyBar.trade_date <= end_date)

    bars = list(db.scalars(stmt).all())
    if limit is not None:
        bars = bars[-limit:]
    return _bars_to_dataframe(bars, adjusted=adjusted)


def get_bars_for_codes(
    db: Session,
    codes: list[str],
    start_date: date | None = None,
    end_date: date | None = None,
    *,
    adjusted: bool = False,
) -> pd.DataFrame:
    """Fetch daily bars for multiple instruments."""
    if not codes:
        return _bars_to_dataframe([], adjusted=adjusted)

    stmt = (
        select(InstrumentDailyBar)
        .where(InstrumentDailyBar.etf_code.in_(codes))
        .order_by(InstrumentDailyBar.etf_code, InstrumentDailyBar.trade_date.asc())
    )
    if start_date is not None:
        stmt = stmt.where(InstrumentDailyBar.trade_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(InstrumentDailyBar.trade_date <= end_date)

    bars = list(db.scalars(stmt).all())
    return _bars_to_dataframe(bars, adjusted=adjusted)


def get_latest_bar(db: Session, code: str) -> InstrumentDailyBar | None:
    """Return the most recent daily bar for an instrument, or None."""
    stmt = (
        select(InstrumentDailyBar)
        .where(InstrumentDailyBar.etf_code == code)
        .order_by(InstrumentDailyBar.trade_date.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def get_latest_bars(db: Session, codes: list[str] | None = None) -> dict[str, InstrumentDailyBar]:
    """Return the latest bar per instrument.

    If ``codes`` is provided, only those instruments are considered.
    """
    subq = (
        select(
            InstrumentDailyBar.etf_code,
            func.max(InstrumentDailyBar.trade_date).label("max_date"),
        )
        .group_by(InstrumentDailyBar.etf_code)
    )
    if codes:
        subq = subq.where(InstrumentDailyBar.etf_code.in_(codes))
    subq = subq.subquery()

    stmt = (
        select(InstrumentDailyBar)
        .join(
            subq,
            (InstrumentDailyBar.etf_code == subq.c.etf_code)
            & (InstrumentDailyBar.trade_date == subq.c.max_date),
        )
    )
    return {bar.etf_code: bar for bar in db.scalars(stmt).all()}


def get_list_date(db: Session, code: str) -> date | None:
    """Return the listing date for an instrument if known."""
    info = db.get(ETFInfo, code)
    if info is None:
        return None
    return info.list_date or info.inception_date


def get_delist_date(db: Session, code: str) -> date | None:
    """Return the delisting date for an instrument if known (None if still active)."""
    info = db.get(ETFInfo, code)
    if info is None:
        return None
    return info.delist_date


def is_before_list_date(db: Session, code: str, query_date: date) -> bool:
    """Return True if ``query_date`` is before the instrument's listing date."""
    list_date = get_list_date(db, code)
    if list_date is None:
        return False
    return query_date < list_date
