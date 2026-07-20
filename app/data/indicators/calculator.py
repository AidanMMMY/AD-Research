"""Batch indicator calculator.

Provides functions for computing technical and risk indicators
for single or multiple ETFs, with database UPSERT support.

Two backends are available:

* ``INDICATOR_BACKEND=pandas`` (default) — original pandas path.
  ~0.15 s per ETF, dominated by ``pandas.rolling.apply`` with
  Python lambdas for drawdown / Sharpe. Times out on the full
  ~7 k A-share ETF universe.
* ``INDICATOR_BACKEND=sql`` — single PostgreSQL query per batch
  that uses window functions and recursive CTEs to compute every
  indicator in the database. ~30 s wall-clock for the full
  universe (≈ 30 × speed-up). All 21 columns match the pandas
  output within 1e-12 relative tolerance (verified via
  ``parity_check.py``).

Set the backend via the ``INDICATOR_BACKEND`` env var (read at
call time so the operator can A/B test without a redeploy).
"""

import logging
import os
import time
from datetime import date, datetime
from typing import Iterable

import pandas as pd
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.cache import cache_invalidate_pattern
from app.data.indicators.market_config import get_market_config, normalise_market
from app.data.indicators.risk import calculate_return_indicators, calculate_risk_indicators
from app.data.indicators.technical import calculate_technical_indicators
from app.models.etf import InstrumentDailyBar, ETFIndicator, ETFInfo
from app.models.etl import ETLLog

logger = logging.getLogger(__name__)

# Minimum number of bars required for meaningful indicator calculation
_MIN_BARS = 5

# Backend selection. Default is ``pandas`` — the per-ETF loop is robust
# across environments and gracefully handles ETFs with no daily-bar
# history (US/crypto listings the scheduler hasn't caught up to).  Set
# ``INDICATOR_BACKEND=sql`` to use the single-query SQL calculator in
# :mod:`app.data.indicators.sql_calculator`; it is ~50x faster on ECS
# when stable, but still being hardened against stalls on some local
# Docker Postgres setups.
INDICATOR_BACKEND: str = os.environ.get("INDICATOR_BACKEND", "pandas").lower()

# Maximum codes per SQL batch. The recursive CTEs walk per etf_code,
# and Postgres' plan time grows superlinearly past ~30 codes per
# query (the six recursive chains in app/data/indicators/sql_calculator
# are O(N²) on chunk size, so a chunk of 100 once took 5+ min and
# never returned).  We default to 20 to keep each individual query
# well under 30 s on the 7.1 GB ECS instance.  Override via env var
# if you need finer control (e.g. INDICATOR_SQL_CHUNK_SIZE=10 on
# a smaller box, or =50 on a beefier one).  Prefix-specific overrides
# are resolved by ``_get_sql_chunk_size_for_prefix`` below.


def _get_sql_chunk_size_for_prefix(prefix: str | None) -> int:
    """Resolve the per-prefix SQL chunk size.

    ``INDICATOR_SQL_CHUNK_SIZE`` sets the global default. Operators can
    override individual prefixes with ``INDICATOR_SQL_CHUNK_SIZE_PREFIX_<P>``.
    Prefix ``6`` (Shanghai-listed A-shares) defaults to 15 because the
    2026-07-15 catch-up showed that shard is the densest and most likely
    to exceed the 600 s per-chunk budget when using the default size of 20.
    """
    default = int(os.environ.get("INDICATOR_SQL_CHUNK_SIZE", "20"))
    if not prefix:
        return default
    override = os.environ.get(f"INDICATOR_SQL_CHUNK_SIZE_PREFIX_{prefix}")
    if override:
        return int(override)
    if prefix == "6":
        return 15
    return default


def _iter_code_chunks(
    codes: list[str], prefix_hint: str | list[str] | None
) -> Iterable[tuple[str, list[str]]]:
    """Yield ``(prefix, chunk)`` pairs for SQL backend execution.

    When a single prefix is hinted (e.g. ``code_prefix='6'``), all codes
    are chunked with that prefix's size. Otherwise codes are grouped by
    their first character so each prefix can use its own chunk size and
    a single mixed-market task does not force a one-size-fits-all plan.
    """
    if isinstance(prefix_hint, str):
        size = _get_sql_chunk_size_for_prefix(prefix_hint)
        for i in range(0, len(codes), size):
            yield prefix_hint, codes[i : i + size]
        return

    by_prefix: dict[str, list[str]] = {}
    for c in codes:
        by_prefix.setdefault(c[0] if c else "", []).append(c)
    for prefix, p_codes in sorted(by_prefix.items()):
        size = _get_sql_chunk_size_for_prefix(prefix)
        for i in range(0, len(p_codes), size):
            yield prefix, p_codes[i : i + size]


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


# Return / drawdown columns widened to DECIMAL(18, 6).  Used by
# ``_build_indicator_record`` to clamp extreme values before upsert
# so a single outlier (e.g. 600601.SH style returns) cannot fail the
# whole indicator chunk.
_RETURN_DRAWDOWN_COLUMNS: dict[str, tuple[int, int]] = {
    "max_drawdown_1y": (18, 6),
    "return_1w": (18, 6),
    "return_1m": (18, 6),
    "return_3m": (18, 6),
    "return_6m": (18, 6),
    "return_1y": (18, 6),
}


def _clamp_decimal(value: float, precision: int, scale: int) -> float:
    """把 float 截断到 DECIMAL(precision, scale) 可表达的范围.

    最大可表示绝对值为 ``10^(precision - scale) - 10^(-scale)``。
    超出时返回边界值，避免 upsert 阶段触发 numeric field overflow。
    """
    max_val = 10 ** (precision - scale) - 10 ** (-scale)
    if value > max_val:
        return max_val
    if value < -max_val:
        return -max_val
    return value


def _safe_float(value, precision: int | None = None, scale: int | None = None) -> float | None:
    """Convert a value to float, returning None for NaN/inf.

    如果提供 ``precision`` 与 ``scale``，则进一步截断到 DECIMAL(precision, scale)
    可表达的最大值，从源头防止极端收益/回撤导致整个 upsert chunk 失败。
    """
    if value is None or pd.isna(value):
        return None
    if isinstance(value, int | float):
        if pd.isna(value) or (isinstance(value, float) and (value == float("inf") or value == float("-inf"))):
            return None
        f = float(value)
    else:
        try:
            f = float(value)
        except (TypeError, ValueError):
            return None
        if pd.isna(f) or f == float("inf") or f == float("-inf"):
            return None

    if precision is not None and scale is not None:
        return _clamp_decimal(f, precision, scale)
    return f


def calculate_single_etf(
    etf_code: str,
    bars_df: pd.DataFrame,
    *,
    market: str = "A股",
    config: object | None = None,
) -> pd.DataFrame:
    """Calculate all indicators for a single ETF.

    Args:
        etf_code: ETF code (used for logging / context only).
        bars_df: DataFrame with columns trade_date, open, high, low,
            close (raw market price), qfq_close (前复权 close),
            volume, amount. Must be sorted by trade_date ascending.
        market: Market key used to select the correct windows and
            annualisation factor when ``config`` is not provided.
        config: Optional ``MarketIndicatorConfig`` overriding the
            market lookup.

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

    # Synthesise qfq_close if the caller did not provide it. This keeps
    # backfill scripts and external callers working even when they only
    # have raw close + adj_factor.
    if "qfq_close" not in df.columns:
        adj_factor = df.get("adj_factor", pd.Series(1.0, index=df.index))
        latest_adj_factor = float(adj_factor.iloc[-1] if len(adj_factor) else 1.0)
        df["qfq_close"] = (
            df["close"].astype(float)
            * adj_factor.astype(float)
            / latest_adj_factor
        )

    # All indicators are now computed on the 前复权 close so that
    # technical, risk, and return metrics stay comparable across
    # splits / dividends / corporate actions while anchoring to the
    # latest market price level.
    qfq_df = df[["trade_date", "open", "high", "low", "qfq_close", "volume", "amount"]].copy()
    qfq_df = qfq_df.rename(columns={"qfq_close": "close"})

    if config is None:
        config = get_market_config(market)

    qfq_df = calculate_technical_indicators(qfq_df, market=market, config=config)
    qfq_df = calculate_risk_indicators(qfq_df, market=market, config=config)
    qfq_df = calculate_return_indicators(qfq_df, market=market, config=config)

    return qfq_df


def _build_indicator_record(etf_code: str, row: pd.Series) -> dict:
    """Build a dict suitable for inserting into ETFIndicator from a DataFrame row."""
    record = {
        "etf_code": etf_code,
        "trade_date": row["trade_date"],
    }
    for col in _INDICATOR_COLUMNS:
        precision, scale = _RETURN_DRAWDOWN_COLUMNS.get(col, (None, None))
        record[col] = _safe_float(row.get(col), precision=precision, scale=scale)
    return record


def _drop_empty_indicator_rows(
    records: list[dict], *, origin: str = "indicator_calc[sql]"
) -> list[dict]:
    """Drop indicator rows where every indicator column is ``None``.

    Defensive upsert: ensures we never write a meaningless all-NULL
    row for a code that, despite passing through the SQL chunk, ends
    up with no bar data on the target date (e.g. recently listed
    crypto ETFs the daily-bar scheduler hasn't caught up to yet —
    NEAR.US, PEPE.US, WIF.US, BONK.US).

    Returns the filtered list. Each dropped record is logged at
    INFO so the operator can audit which codes were filtered out.
    """
    kept: list[dict] = []
    for record in records:
        all_null = all(record.get(col) is None for col in _INDICATOR_COLUMNS)
        if all_null:
            logger.info(
                "%s: skipped empty result for code=%s date=%s "
                "(all %d indicators NULL)",
                origin,
                record.get("etf_code"),
                record.get("trade_date"),
                len(_INDICATOR_COLUMNS),
            )
            continue
        kept.append(record)
    return kept


# ETLLog job names per market, matching the scheduler job ids tracked by
# the ops dashboard (app/api/v1/etl_status.py). Markets not listed here
# (and unfiltered/manual runs) keep the legacy "indicator_calc" name.
_ETL_JOB_NAMES = {
    "A股": "indicator_calculation",
    "US": "us_indicator_calculation",
    "CRYPTO": "crypto_indicator_calculation",
}


def batch_calculate_indicators(
    db: Session,
    target_date: date | None = None,
    full_history: bool = False,
    market_filter: str | None = None,
    instrument_type_filter: str | None = None,
    code_prefix: str | list[str] | None = None,
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
        instrument_type_filter: If provided (e.g. ``"ETF"``,
            ``"STOCK"``), narrow the universe to that ``instrument_type``
            *within* the requested market. Defaults to ``None`` (no
            extra filter — preserves the original behaviour where
            ``market_filter='A股'`` covers both ETFs and stocks in one
            pass).
        code_prefix: If provided, only process codes whose ``etf_code``
            starts with this prefix. Useful for sharding a large market
            (e.g. A-share stocks) across multiple workers.

    Returns:
        Number of indicator records updated/inserted.
    """
    start_time = datetime.now()
    updated_count = 0
    errors = []

    # Resolve the ETLLog job name for the requested market (see
    # _ETL_JOB_NAMES) so the ops dashboard can attribute this run.
    job_name = _ETL_JOB_NAMES.get(market_filter, "indicator_calc")

    # Query all active ETFs, optionally filtering by market
    # Exclude delisted instruments (delist_date < target_date)
    stmt = select(
        ETFInfo.code,
        ETFInfo.list_date,
        ETFInfo.inception_date,
        ETFInfo.delist_date,
        ETFInfo.market,
    ).where(ETFInfo.status == "active")
    if market_filter is not None:
        stmt = stmt.where(ETFInfo.market == market_filter)
    if instrument_type_filter is not None:
        stmt = stmt.where(ETFInfo.instrument_type == instrument_type_filter)
    if code_prefix is not None:
        prefixes = [code_prefix] if isinstance(code_prefix, str) else code_prefix
        stmt = stmt.where(or_(*[ETFInfo.code.like(f"{p}%") for p in prefixes]))
    active_rows = db.execute(stmt).all()

    if not active_rows:
        # Log and return 0
        _log_etl(db, job_name, "success", 0, start_time, None)
        return 0

    # Group by market so each path (SQL/pandas) can use the correct
    # MarketIndicatorConfig (windows, annualisation factor, min_periods).
    by_market: dict[str, list] = {}
    for r in active_rows:
        by_market.setdefault(normalise_market(r.market), []).append(r)

    effective_target = target_date if target_date is not None else date.today()

    # Fast path: single-query SQL backend. Skip per-ETF date checks
    # (the SQL handles ``target_date`` filtering) and dispatch per market
    # so each query uses the right window sizes. Pandas path keeps the
    # listing-date / delisted-date guards because it fetches bars per-ETF.
    if INDICATOR_BACKEND == "sql":
        for market, market_rows in by_market.items():
            code_meta = {
                r.code: (r.list_date or r.inception_date, r.delist_date, market)
                for r in market_rows
            }
            # Pre-filter to codes that actually have daily bars on or before
            # the target date.  This avoids setting up recursive CTE partitions
            # for thousands of recently-listed US/crypto ETFs that the daily-bar
            # scheduler hasn't caught up to yet, which is the dominant cause of
            # the local-Docker stalls seen during full-market runs.
            codes_with_bars = {
                row[0]
                for row in db.execute(
                    select(InstrumentDailyBar.etf_code).distinct().where(
                        InstrumentDailyBar.etf_code.in_(code_meta.keys()),
                        InstrumentDailyBar.trade_date <= effective_target,
                    )
                )
            }
            codes = [c for c in code_meta if c in codes_with_bars]
            logger.info(
                "indicator_calc[sql] backend=%s market=%s active=%d with_bars=%d target=%s full_history=%s instrument_type=%s code_prefix=%s",
                INDICATOR_BACKEND,
                market,
                len(code_meta),
                len(codes),
                target_date,
                full_history,
                instrument_type_filter,
                code_prefix,
            )
            try:
                updated_count += _batch_calculate_indicators_sql(
                    db,
                    codes,
                    code_meta,
                    target_date=target_date,
                    full_history=full_history,
                    code_prefix=code_prefix,
                    market=market,
                )
            except Exception as exc:
                errors.append(f"sql-backend-{market}: {exc}")
                logger.exception("indicator_calc[sql] failed for %s: %s", market, exc)

        # Final cache invalidation (also run for the SQL path).
        try:
            cache_invalidate_pattern("indicator:*")
            cache_invalidate_pattern("screen:*")
        except Exception:
            logger.exception("Failed to invalidate indicator/screen caches")

        status = "success" if not errors else "partial"
        error_msg = "\n".join(errors) if errors else None
        _log_etl(db, job_name, status, updated_count, start_time, error_msg)
        return updated_count

    for market, market_rows in by_market.items():
        for row in market_rows:
            etf_code = row.code
            list_date = row.list_date or row.inception_date
            delist_date = row.delist_date

            records = _calculate_single_code_pandas(
                db, etf_code, list_date, delist_date, target_date, full_history, market=market
            )
            if not records:
                continue

            try:
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
    _log_etl(db, job_name, status, updated_count, start_time, error_msg)

    return updated_count

def _calculate_single_code_pandas(
    db: Session,
    etf_code: str,
    list_date: date | None,
    delist_date: date | None,
    target_date: date | None,
    full_history: bool,
    *,
    market: str = "A股",
) -> list[dict]:
    """Calculate indicators for a single ETF using the pandas path.

    Returns a list of upsert-ready records (possibly empty).  Does not
    commit or write to the DB — the caller owns the transaction.
    """
    # Skip instruments that are not yet listed as of the target date.
    if target_date is not None and list_date is not None and target_date < list_date:
        return []

    # Skip instruments that were delisted before the target date.
    if target_date is not None and delist_date is not None and target_date > delist_date:
        return []

    try:
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
            return []

        latest_adj_factor = float(bars[-1].adj_factor or 1.0)

        df = pd.DataFrame(
            [
                {
                    "trade_date": b.trade_date,
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": float(b.close),
                    "qfq_close": float(b.close) * float(b.adj_factor or 1.0) / latest_adj_factor,
                    "volume": b.volume,
                    "amount": b.amount,
                }
                for b in bars
            ]
        )

        result_df = calculate_single_etf(etf_code, df, market=market)
        if result_df.empty:
            return []

        if full_history:
            records = [
                _build_indicator_record(etf_code, row)
                for _, row in result_df.iterrows()
            ]
        else:
            latest_row = result_df.iloc[-1]
            records = [_build_indicator_record(etf_code, latest_row)]

        return _drop_empty_indicator_rows(records, origin="indicator_calc[pandas-fallback]")
    except Exception:
        logger.exception("indicator_calc[pandas-fallback]: failed for %s", etf_code)
        return []


def _batch_calculate_indicators_sql(
    db: Session,
    codes: list[str],
    code_meta: dict[str, tuple[date | None, date | None, str]],
    *,
    target_date: date | None,
    full_history: bool,
    code_prefix: str | list[str] | None = None,
    market: str = "A股",
) -> int:
    """SQL-backend path: chunked single-query execution + UPSERT.

    Iterates the codes in prefix-aware chunks, runs
    ``sql_calculate_latest`` / ``sql_calculate_full_history`` for
    each chunk, and UPSERTs the rows into ``etf_indicator``.

    If a chunk times out or otherwise fails, it is automatically
    retried one code at a time through the pandas path so the batch
    as a whole still makes progress.

    Returns the number of records written.
    """
    # Local import to keep the pandas path independent of the SQL
    # module (so tests can monkeypatch / avoid loading the SQL
    # query template if Postgres isn't available).
    from app.data.indicators.sql_calculator import (
        build_indicator_payload,
        sql_calculate_full_history,
        sql_calculate_latest,
    )

    if not codes:
        return 0

    updated_count = 0
    fallback_count = 0
    runner = sql_calculate_full_history if full_history else sql_calculate_latest

    chunk_index = 0
    for prefix, chunk in _iter_code_chunks(codes, code_prefix):
        chunk_index += 1
        logger.info(
            "indicator_calc[sql]: processing chunk %d prefix=%s size=%d / total=%d",
            chunk_index,
            prefix,
            len(chunk),
            len(codes),
        )
        t0 = time.perf_counter()
        try:
            rows = runner(db, chunk, target_date=target_date, market=market)
            elapsed = time.perf_counter() - t0
            records = [build_indicator_payload(r) for r in rows]
            # Defensive upsert: drop any record that came back all-NULL
            # (e.g. a code whose bars CTE partition ended up empty
            # because the daily-bar scheduler hasn't written rows yet).
            # ``_drop_empty_indicator_rows`` logs each skip so we have
            # a paper trail for what got filtered.
            records = _drop_empty_indicator_rows(records)
            logger.info(
                "indicator_calc[sql]: chunk %d prefix=%s rows=%d elapsed=%.3fs",
                chunk_index,
                prefix,
                len(records),
                elapsed,
            )
            if not records:
                continue
            insert_stmt = insert(ETFIndicator).values(records)
            upsert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=["etf_code", "trade_date"],
                set_={col: insert_stmt.excluded[col] for col in _INDICATOR_COLUMNS},
            )
            db.execute(upsert_stmt)
            db.commit()
            updated_count += len(records)
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            db.rollback()
            logger.warning(
                "indicator_calc[sql]: chunk %d prefix=%s failed after %.3fs (%s), "
                "falling back to pandas for %d codes",
                chunk_index,
                prefix,
                elapsed,
                exc,
                len(chunk),
            )
            for etf_code in chunk:
                list_date, delist_date, _market = code_meta.get(
                    etf_code, (None, None, market)
                )
                records = _calculate_single_code_pandas(
                    db, etf_code, list_date, delist_date, target_date, full_history, market=_market
                )
                if not records:
                    continue
                try:
                    insert_stmt = insert(ETFIndicator).values(records)
                    upsert_stmt = insert_stmt.on_conflict_do_update(
                        index_elements=["etf_code", "trade_date"],
                        set_={col: insert_stmt.excluded[col] for col in _INDICATOR_COLUMNS},
                    )
                    db.execute(upsert_stmt)
                    db.commit()
                    updated_count += len(records)
                    fallback_count += len(records)
                except Exception as exc2:
                    db.rollback()
                    logger.exception(
                        "indicator_calc[sql]: pandas fallback also failed for %s: %s",
                        etf_code,
                        exc2,
                    )

    logger.info(
        "indicator_calc[sql]: finished; updated=%d fallback_records=%d",
        updated_count,
        fallback_count,
    )
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
