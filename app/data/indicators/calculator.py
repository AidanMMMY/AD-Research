"""Batch indicator calculator.

Provides functions for computing technical and risk indicators
for single or multiple ETFs, with database UPSERT support.
"""

import logging
from datetime import date, datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.cache import cache_invalidate_pattern
from app.data.indicators.risk import calculate_risk_indicators
from app.data.indicators.technical import calculate_technical_indicators
from app.models.etf import ETFDailyBar, ETFIndicator, ETFInfo
from app.models.etl import ETLLog

logger = logging.getLogger(__name__)

# Minimum number of bars required for meaningful indicator calculation
_MIN_BARS = 5

# Mapping of DataFrame column names to ETFIndicator model attribute names
_INDICATOR_COLUMNS = [
    "ma5",
    "ma10",
    "ma20",
    "ma60",
    "rsi14",
    "macd_dif",
    "macd_dea",
    "macd_hist",
    "atr14",
    "bb_upper",
    "bb_lower",
    "volatility_20d",
    "volatility_60d",
    "max_drawdown_1y",
    "sharpe_1y",
    "return_1w",
    "return_1m",
    "return_3m",
    "return_6m",
    "return_1y",
    "amount",
]


def _safe_float(value) -> float | None:
    """Convert a value to float, returning None for NaN/inf."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, int | float):
        if pd.isna(value) or (isinstance(value, float) and (value == float("inf") or value == float("-inf"))):
            return None
        return float(value)
    try:
        f = float(value)
        if pd.isna(f) or f == float("inf") or f == float("-inf"):
            return None
        return f
    except (TypeError, ValueError):
        return None


def calculate_single_etf(etf_code: str, bars_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all indicators for a single ETF.

    Args:
        etf_code: ETF code (used for logging / context only).
        bars_df: DataFrame with columns trade_date, open, high, low,
            close, volume. Must be sorted by trade_date ascending.

    Returns:
        DataFrame with all indicator columns appended. Returns an empty
        DataFrame if there are fewer than 5 rows of data.
    """
    if bars_df is None or len(bars_df) < _MIN_BARS:
        return pd.DataFrame()

    df = bars_df.copy()

    # Sort by trade_date to ensure chronological order
    if "trade_date" in df.columns:
        df = df.sort_values("trade_date").reset_index(drop=True)

    # Calculate technical indicators first
    df = calculate_technical_indicators(df)

    # Then calculate risk indicators
    df = calculate_risk_indicators(df)

    return df


def _build_indicator_record(etf_code: str, row: pd.Series) -> dict:
    """Build a dict suitable for inserting into ETFIndicator from a DataFrame row."""
    record = {
        "etf_code": etf_code,
        "trade_date": row["trade_date"],
    }
    for col in _INDICATOR_COLUMNS:
        record[col] = _safe_float(row.get(col))
    return record


def batch_calculate_indicators(
    db: Session,
    target_date: date | None = None,
    full_history: bool = False,
    market_filter: str | None = None,
) -> int:
    """Batch-calculate indicators for all active ETFs.

    For each active ETF, fetches all historical daily bars, computes
    technical and risk indicators, and UPSERTs them into the
    etf_indicator table.

    Args:
        db: SQLAlchemy database session.
        target_date: If provided, only compute indicators up to and
            including this date. If None, use all available data.
        full_history: If True, upsert indicators for every historical
            trade date instead of only the latest day. Useful for
            backfilling missing indicator history.
        market_filter: If provided (e.g. ``"CRYPTO"``, ``"US"``),
            only calculate indicators for instruments in that market.
            If None, calculate for all active instruments.

    Returns:
        Number of indicator records updated/inserted.
    """
    start_time = datetime.now()
    updated_count = 0
    errors = []

    # Query all active ETFs, optionally filtering by market
    stmt = select(ETFInfo.code).where(ETFInfo.status == "active")
    if market_filter is not None:
        stmt = stmt.where(ETFInfo.market == market_filter)
    active_etfs = db.execute(stmt).scalars().all()

    if not active_etfs:
        # Log and return 0
        _log_etl(db, "indicator_calc", "success", 0, start_time, None)
        return 0

    for etf_code in active_etfs:
        try:
            # Fetch all historical bars for this ETF
            stmt = (
                select(ETFDailyBar)
                .where(ETFDailyBar.etf_code == etf_code)
                .order_by(ETFDailyBar.trade_date.asc())
            )
            if target_date is not None:
                stmt = stmt.where(ETFDailyBar.trade_date <= target_date)

            bars = db.execute(stmt).scalars().all()

            if not bars or len(bars) < _MIN_BARS:
                continue

            # Convert to DataFrame
            df = pd.DataFrame(
                [
                    {
                        "trade_date": b.trade_date,
                        "open": b.open,
                        "high": b.high,
                        "low": b.low,
                        "close": b.close,
                        "volume": b.volume,
                        "amount": b.amount,
                    }
                    for b in bars
                ]
            )

            # Calculate indicators
            result_df = calculate_single_etf(etf_code, df)

            if result_df.empty:
                continue

            if full_history:
                # Upsert indicators for every historical row that has data
                records = [
                    _build_indicator_record(etf_code, row)
                    for _, row in result_df.iterrows()
                ]
            else:
                # Keep only the latest day's record
                latest_row = result_df.iloc[-1]
                records = [_build_indicator_record(etf_code, latest_row)]

            if not records:
                continue

            # Bulk UPSERT into etf_indicator table
            insert_stmt = insert(ETFIndicator).values(records)
            upsert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=["etf_code", "trade_date"],
                set_={col: insert_stmt.excluded[col] for col in _INDICATOR_COLUMNS},
            )
            db.execute(upsert_stmt)
            db.commit()
            updated_count += len(records)

        except Exception as exc:
            db.rollback()
            errors.append(f"{etf_code}: {exc}")
            # Continue with next ETF
            continue

    # Final cache invalidation (outside the per-ETF loop)
    try:
        cache_invalidate_pattern("indicator:*")
        cache_invalidate_pattern("screen:*")
    except Exception:
        logger.exception("Failed to invalidate indicator/screen caches")

    # Record ETL log
    status = "success" if not errors else "partial"
    error_msg = "\n".join(errors) if errors else None
    _log_etl(db, "indicator_calc", status, updated_count, start_time, error_msg)

    return updated_count


def _log_etl(
    db: Session,
    job_name: str,
    status: str,
    records_count: int,
    start_time: datetime,
    error_msg: str | None,
) -> None:
    """Write an ETLLog entry and commit."""
    log = ETLLog(
        job_name=job_name,
        status=status,
        start_time=start_time,
        end_time=datetime.now(),
        records_count=records_count,
        error_msg=error_msg,
    )
    db.add(log)
    db.commit()
