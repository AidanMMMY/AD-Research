"""Regression tests for the A-share stock daily bar upsert (``AStockDailyPipeline.load``).

Same production failure class as ``a_share_daily_etl`` (2026-07-16, see
test_a_share_daily_upsert.py): dropping None keys per row yields heterogeneous
multi-row VALUES, so SQLAlchemy renders the missing column as a per-row bound
parameter and the ON CONFLICT DO UPDATE statement fails to compile.  The fix
mirrors ``a_share.py``: uniform keys with None-filled NULLs and a CASE-guarded
DO UPDATE SET.  These tests compile the emitted statement against the
PostgreSQL dialect, which is where the failure surfaces.
"""

from datetime import date
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
from sqlalchemy.dialects import postgresql

from app.data.pipelines.a_share_stock_daily import AStockDailyPipeline

_TRADE_DATE = date(2026, 7, 17)


def _load_and_compile(df: pd.DataFrame) -> str:
    """Run ``load()`` against a mock session and compile the emitted statement."""
    db = MagicMock()
    pipeline = AStockDailyPipeline.__new__(AStockDailyPipeline)
    pipeline.db = db
    pipeline._load_adj_factor_history = MagicMock()
    pipeline.load(df)
    stmt = db.execute.call_args[0][0]
    return str(stmt.compile(dialect=postgresql.dialect()))


def _mixed_nulls_df() -> pd.DataFrame:
    """The failure shape: one row missing change_pct/turnover_rate."""
    return pd.DataFrame(
        [
            {
                "etf_code": "600519.SH",
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
                "etf_code": "000001.SZ",
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
    """Rows with inconsistent NULL fields must not break ON CONFLICT compilation."""
    sql = _load_and_compile(_mixed_nulls_df())
    assert "change_pct" in sql
    assert "change_pct = CASE" in sql


def test_upsert_compiles_when_column_all_null():
    """An all-NULL column stays in VALUES but is left out of SET."""
    sql = _load_and_compile(_mixed_nulls_df().assign(change_pct=np.nan))
    assert "change_pct" in sql
    assert "change_pct = CASE" not in sql


def test_upsert_compiles_when_column_absent_from_frame():
    """A column missing from the source frame entirely must also compile."""
    sql = _load_and_compile(_mixed_nulls_df().drop(columns=["change_pct"]))
    assert "change_pct" not in sql
    assert "adj_factor = CASE" in sql
