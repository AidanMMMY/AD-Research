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
from app.data.indicators.risk import calculate_return_indicators, calculate_risk_indicators
from app.data.indicators.technical import calculate_technical_indicators
from app.models.etf import InstrumentDailyBar, ETFIndicator, ETFInfo
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
            close (raw market price), adj_close (split/dividend adjusted),
            volume, amount. Must be sorted by trade_date ascending.

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

    # Technical indicators (MA/RSI/MACD/Bollinger/ATR) are computed on raw
    # close so they align with the market price users see in the UI.
    raw_df = df[["trade_date", "open", "high", "low", "close", "volume", "amount"]].copy()
    raw_df = calculate_technical_indicators(raw_df)

    # Volatility / drawdown / Sharpe are computed on the dividend-adjusted
    # close so long-window metrics stay comparable across corporate actions.
    adj_df = df[["trade_date", "open", "high", "low", "adj_close", "volume", "amount"]].copy()
    adj_df = adj_df.rename(columns={"adj_close": "close"})
    adj_df = calculate_risk_indicators(adj_df)

    # Period returns are computed on the **raw** close, NOT adj_close.
    # Rationale: the recent adj_factor normalisation makes historical
    # adj_factor values < 1.0 for every older date, so adj_close for an
    # older bar equals ``close * factor < close``. Computing the return as
    # ``adj_close[latest] / adj_close[old] - 1`` then bakes future dividend
    # yields into the divisor — that is "total-return" semantics, which
    # flattens (or even flips the sign of) the displayed 1m / 3m / 1y
    # numbers whenever a dividend lands inside the lookback window. For
    # ETF 512760.SH this dropped the 1m return from a few-percent move
    # down to 0.71 %, which is exactly the regression the bug report
    # flags. Use raw close so the UI shows the price-return view users
    # expect from a market chart.
    raw_df = calculate_return_indicators(raw_df)

    # Merge: keep OHLCV from raw price space; append technical columns
    # from raw_df, vol/drawdown/Sharpe from adj_df, and period returns
    # from raw_df (overwriting whatever adj_df produced — those were the
    # wrong, adj_close-based values).
    result = raw_df.copy()
    risk_cols = [c for c in adj_df.columns if c not in result.columns and c != "daily_return"]
    for col in risk_cols:
        result[col] = adj_df[col].values

    return result


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
    # Exclude delisted instruments (delist_date < target_date)
    stmt = select(
        ETFInfo.code,
        ETFInfo.list_date,
        ETFInfo.inception_date,
        ETFInfo.delist_date,
    ).where(ETFInfo.status == "active")
    if market_filter is not None:
        stmt = stmt.where(ETFInfo.market == market_filter)
    active_rows = db.execute(stmt).all()

    if not active_rows:
        # Log and return 0
        _log_etl(db, "indicator_calc", "success", 0, start_time, None)
        return 0

    for row in active_rows:
        etf_code = row.code
        list_date = row.list_date or row.inception_date
        delist_date = row.delist_date

        # Skip instruments that are not yet listed as of the target date.
        if target_date is not None and list_date is not None and target_date < list_date:
            continue

        # Skip instruments that were delisted before the target date.
        if target_date is not None and delist_date is not None and target_date > delist_date:
            continue

        try:
            # Fetch all historical bars for this ETF, starting from listing date
            stmt = (
                select(InstrumentDailyBar)
                .where(InstrumentDailyBar.etf_code == etf_code)
                .order_by(InstrumentDailyBar.trade_date.asc())
            )
            if list_date is not None:
                stmt = stmt.where(InstrumentDailyBar.trade_date >= list_date)
            if target_date is not None:
                stmt = stmt.where(InstrumentDailyBar.trade_date <= target_date)

            bars = db.execute(stmt).scalars().all()

            if not bars or len(bars) < _MIN_BARS:
                continue

            # Convert to DataFrame.  Keep both raw close (for technical
            # indicators that users compare to market price) and adjusted
            # close (for risk/return metrics that must be comparable over
            # time after splits/dividends).
            df = pd.DataFrame(
                [
                    {
                        "trade_date": b.trade_date,
                        "open": b.open,
                        "high": b.high,
                        "low": b.low,
                        "close": float(b.close),
                        "adj_close": float(b.close) * float(b.adj_factor or 1.0),
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
