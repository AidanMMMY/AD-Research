"""Tests for the etf_holding FK guard in ETFHoldingsPipeline.load().

Regression: the Tushare bulk pull returns the whole market for a period
(including OTC ``.OF`` funds outside the requested whitelist). Rows whose
``etf_code`` is not present in ``etf_info`` violate the
``etf_holding_etf_code_fkey`` FK and used to fail the entire upsert batch.
``load()`` must drop those rows instead.
"""

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from app.data.pipelines.etf_holdings import ETFHoldingsPipeline
from app.models.etf import ETFInfo


class _FakeInsert:
    """Stand-in for the PostgreSQL ``insert`` statement (SQLite can't
    compile ``ON CONFLICT``), capturing the rows passed to ``values``."""

    def __init__(self, table):
        self.table = table
        self.rows = None
        self.excluded = SimpleNamespace(
            holding_name=None,
            weight=None,
            shares=None,
            market_value=None,
            holdings_as_of_date=None,
            source=None,
        )

    def values(self, rows):
        self.rows = rows
        return self

    def on_conflict_do_update(self, **kwargs):
        return self


def _holdings_df(rows):
    base = {
        "holding_code": "600519",
        "holding_name": "贵州茅台",
        "weight": 0.05,
        "shares": 100.0,
        "market_value": 1_000_000.0,
        "snapshot_date": date(2026, 6, 30),
        "source": "tushare",
    }
    return pd.DataFrame([{**base, "etf_code": code} for code in rows])


@pytest.fixture
def pipeline(db_session, monkeypatch):
    db_session.add(ETFInfo(code="510300.SH", name="沪深300ETF"))
    db_session.commit()

    pipe = ETFHoldingsPipeline(db_session)

    captured: list[_FakeInsert] = []

    def fake_pg_insert(table):
        stmt = _FakeInsert(table)
        captured.append(stmt)
        return stmt

    monkeypatch.setattr(
        "app.data.pipelines.etf_holdings.pg_insert",
        fake_pg_insert,
    )
    # Skip executing the (Postgres-only) statement; just record it.
    # Real statements (ORM queries) pass through to the session.
    real_execute = pipe.db.execute

    def fake_execute(stmt, *args, **kwargs):
        if isinstance(stmt, _FakeInsert):
            captured.append(stmt)
            return None
        return real_execute(stmt, *args, **kwargs)

    monkeypatch.setattr(pipe.db, "execute", fake_execute)
    return pipe, captured


def test_load_drops_etf_codes_missing_from_etf_info(pipeline):
    pipe, captured = pipeline
    df = _holdings_df(["510300.SH", "012496.OF"])

    inserted = pipe.load(df)

    assert inserted == 1
    assert len(captured) == 2  # insert stmt + execute call
    rows = captured[0].rows
    assert [r["etf_code"] for r in rows] == ["510300.SH"]


def test_load_returns_zero_when_no_code_matches(pipeline):
    pipe, captured = pipeline
    df = _holdings_df(["012496.OF", "012497.OF"])

    assert pipe.load(df) == 0
    assert captured == []  # no upsert attempted
