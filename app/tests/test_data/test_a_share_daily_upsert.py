"""Regression tests for the A-share ETF daily bar upsert (``AShareETLPipeline.load``).

Production incident (2026-07-16 to 07-18, job ``a_share_daily_etl``): when some
rows in the batch were missing a value (e.g. ``change_pct`` from a fallback
source), the loader dropped that key from only those rows' dicts.  SQLAlchemy
then rendered the column as a per-row bound parameter in the VALUES clause and
failed to compile the ON CONFLICT DO UPDATE statement with::

    CompileError: INSERT value for column instrument_daily_bar.change_pct is
    explicitly rendered as a bound parameter in the VALUES clause; a
    Python-side value or SQL expression is required

The fix normalizes every record to the same set of keys (NULLs filled with
None) and guards the DO UPDATE SET with a CASE expression.  These tests
compile the exact statement the loader builds against the PostgreSQL dialect,
which is precisely where the production failure occurred (the error is raised
at compile time, before any SQL reaches the database).
"""

from datetime import date
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
from sqlalchemy.dialects import postgresql

from app.data.pipelines.a_share import AShareETLPipeline

_TRADE_DATE = date(2026, 7, 17)


def _load_and_compile(df: pd.DataFrame) -> str:
    """Run ``load()`` against a mock session and compile the emitted statement."""
    db = MagicMock()
    pipeline = AShareETLPipeline.__new__(AShareETLPipeline)
    pipeline.db = db
    pipeline.load(df)
    stmt = db.execute.call_args[0][0]
    return str(stmt.compile(dialect=postgresql.dialect()))


def _mixed_nulls_df() -> pd.DataFrame:
    """The production failure shape: one row missing change_pct/turnover_rate."""
    return pd.DataFrame(
        [
            {
                "etf_code": "510300.SH",
                "trade_date": _TRADE_DATE,
                "open": 1.0,
                "high": 1.1,
                "low": 0.9,
                "close": 1.05,
                "volume": 100,
                "amount": 100.0,
                "pre_close": 1.0,
                "change_pct": 1.0,
                "turnover_rate": 0.1,
                "adj_factor": 1.0,
            },
            {
                "etf_code": "510050.SH",
                "trade_date": _TRADE_DATE,
                "open": 2.0,
                "high": 2.1,
                "low": 1.9,
                "close": 2.05,
                "volume": 200,
                "amount": 200.0,
                "pre_close": 2.0,
                "change_pct": np.nan,
                "turnover_rate": np.nan,
                "adj_factor": 1.0,
            },
        ]
    )


def test_upsert_compiles_with_mixed_null_rows():
    """Rows with inconsistent NULL fields must not break ON CONFLICT compilation.

    Covers both the INSERT VALUES rendering and the DO UPDATE SET rendering of
    ``change_pct`` — the two paths named in the production CompileError.
    """
    sql = _load_and_compile(_mixed_nulls_df())
    # change_pct is in the uniform INSERT column list (not a per-row bound param)
    assert "change_pct" in sql
    # and it is updated on conflict via a NULL-preserving CASE expression
    assert "change_pct = CASE" in sql


def test_upsert_compiles_when_column_all_null():
    """A column that is NULL in every row stays in VALUES but is left out of SET,
    so existing values are preserved on conflict reruns."""
    sql = _load_and_compile(_mixed_nulls_df().assign(change_pct=np.nan))
    assert "change_pct" in sql  # still inserted (as NULL)
    assert "change_pct = CASE" not in sql  # but never overwritten with NULL


def test_upsert_compiles_when_column_absent_from_frame():
    """A column missing from the source frame entirely must also compile."""
    sql = _load_and_compile(_mixed_nulls_df().drop(columns=["change_pct"]))
    assert "change_pct" not in sql
    assert "adj_factor = CASE" in sql
