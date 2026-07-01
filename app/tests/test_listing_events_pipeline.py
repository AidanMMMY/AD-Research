"""Tests for the ListingEventsPipeline.

Focuses on:
- Date coercion (``_coerce_date``) across Tushare input formats.
- Numeric coercion (``_coerce_numeric``).
- ``_to_upsert_dict`` builds a valid record and computes status / market /
  board correctly.
- The full pipeline upserts records idempotently (re-runs do not duplicate
  rows for the same ts_code).
"""

from datetime import date, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from app.data.pipelines.listing_events import (
    ListingEventsPipeline,
    _coerce_date,
    _coerce_numeric,
    _to_upsert_dict,
)
from app.models.listing import ListingEvent


# ---------------------------------------------------------------------------
# _coerce_date
# ---------------------------------------------------------------------------


class TestCoerceDate:
    @pytest.mark.parametrize("value,expected", [
        ("20260115", date(2026, 1, 15)),
        ("2026-01-15", date(2026, 1, 15)),
        ("2026/01/15", date(2026, 1, 15)),
        (date(2026, 1, 15), date(2026, 1, 15)),
        (None, None),
        ("", None),
    ])
    def test_parses_supported_formats(self, value, expected):
        assert _coerce_date(value) == expected

    def test_returns_none_for_invalid_string(self):
        assert _coerce_date("not-a-date") is None
        assert _coerce_date("2026-13-01") is None  # invalid month

    def test_handles_pandas_nat(self):
        # pandas NaT/NaN should become None (avoid TypeError on strptime).
        assert _coerce_date(float("nan")) is None


# ---------------------------------------------------------------------------
# _coerce_numeric
# ---------------------------------------------------------------------------


class TestCoerceNumeric:
    def test_int_and_float(self):
        assert _coerce_numeric(25) == 25.0
        assert _coerce_numeric(25.5) == 25.5

    def test_numeric_string(self):
        assert _coerce_numeric("12.34") == 12.34

    def test_invalid_string_returns_none(self):
        assert _coerce_numeric("not-a-number") is None

    def test_none_and_nan(self):
        assert _coerce_numeric(None) is None
        assert _coerce_numeric(float("nan")) is None


# ---------------------------------------------------------------------------
# _to_upsert_dict
# ---------------------------------------------------------------------------


class TestToUpsertDict:
    def test_minimal_record(self):
        record = {"ts_code": "001289.SZ", "name": "Co"}
        out = _to_upsert_dict(record, today=date(2026, 6, 1))
        assert out is not None
        assert out["ts_code"] == "001289.SZ"
        assert out["name"] == "Co"
        assert out["market"] == "SZ"
        assert out["board"] == "主板"
        assert out["status"] == "unknown"
        assert out["source"] == "tushare"
        assert out["raw_payload"] is record

    def test_full_record_status_listed(self):
        record = {
            "ts_code": "688981.SH",
            "sub_code": "787981",
            "name": "Star Co",
            "industry": "信息技术",
            "ipo_date": "20250101",
            "issue_date": "20250101",
            "list_date": "20250115",
            "price": 88.0,
            "pe": 45.2,
            "limit_amount": 5000.0,
            "funds": 300000.0,
            "market_amount": 10000.0,
            "sponsor": "Sponsor X",
            "underwriter": "Underwriter Y",
        }
        out = _to_upsert_dict(record, today=date(2026, 6, 1))
        assert out["market"] == "SH"
        assert out["board"] == "科创板"
        assert out["industry"] == "信息技术"
        assert out["issue_date"] == date(2025, 1, 1)
        assert out["list_date"] == date(2025, 1, 15)
        assert out["issue_price"] == 88.0
        assert out["pe_ratio"] == 45.2
        assert out["funds_raised"] == 300000.0
        assert out["status"] == "listed"
        assert out["sponsor"] == "Sponsor X"
        assert out["underwriter"] == "Underwriter Y"

    def test_status_upcoming_when_dates_in_future(self):
        future = (date.today() + timedelta(days=30)).strftime("%Y%m%d")
        record = {
            "ts_code": "601999.SH",
            "name": "Future Co",
            "issue_date": future,
            "list_date": future,
        }
        out = _to_upsert_dict(record, today=date.today())
        assert out["status"] == "upcoming"

    def test_status_subscribing_between_issue_and_list(self):
        issue = (date.today() - timedelta(days=2)).strftime("%Y%m%d")
        list_ = (date.today() + timedelta(days=10)).strftime("%Y%m%d")
        record = {
            "ts_code": "601888.SH",
            "name": "Subscribing Co",
            "issue_date": issue,
            "list_date": list_,
        }
        out = _to_upsert_dict(record, today=date.today())
        assert out["status"] == "subscribing"

    def test_missing_ts_code_returns_none(self):
        record = {"name": "NoCode"}
        assert _to_upsert_dict(record, today=date.today()) is None

    def test_missing_name_returns_none(self):
        record = {"ts_code": "601999.SH"}
        assert _to_upsert_dict(record, today=date.today()) is None

    def test_numeric_coercion_handles_strings(self):
        record = {
            "ts_code": "601999.SH",
            "name": "Co",
            "price": "12.50",
            "pe": "23.4",
        }
        out = _to_upsert_dict(record, today=date.today())
        assert out["issue_price"] == 12.5
        assert out["pe_ratio"] == 23.4


# ---------------------------------------------------------------------------
# Pipeline integration: extract/transform/load via mocks + in-memory SQLite
# ---------------------------------------------------------------------------


def _patch_provider_extract(records: list[dict]):
    """Return a context manager that overrides the pipeline's extract()."""
    return patch.object(
        ListingEventsPipeline,
        "extract",
        return_value=records,
    )


SAMPLE_RECORDS = [
    {
        "ts_code": "001289.SZ",
        "sub_code": "001289",
        "name": "Co A",
        "ipo_date": "20260115",
        "issue_date": "20260115",
        "list_date": "20260201",
        "price": 25.5,
        "pe": 22.3,
        "limit_amount": 10000.0,
        "funds": 50000.0,
        "market_amount": 20000.0,
        "industry": "电子",
        "sponsor": "Sponsor A",
        "underwriter": "Underwriter A",
    },
    {
        "ts_code": "688981.SH",
        "sub_code": "787981",
        "name": "Co B",
        "ipo_date": "20260120",
        "issue_date": "20260120",
        "list_date": "20260205",
        "price": 88.0,
        "pe": 45.2,
        "limit_amount": 5000.0,
        "funds": 300000.0,
        "market_amount": 10000.0,
        "industry": "信息技术",
        "sponsor": "Sponsor B",
        "underwriter": "Underwriter B",
    },
]


def test_pipeline_run_inserts_records(db_session):
    with _patch_provider_extract(SAMPLE_RECORDS):
        pipeline = ListingEventsPipeline(db_session)
        result = pipeline.run()

    assert result.success is True
    assert result.records == 2
    rows = db_session.query(ListingEvent).all()
    assert len(rows) == 2
    codes = {r.ts_code for r in rows}
    assert codes == {"001289.SZ", "688981.SH"}


def test_pipeline_run_is_idempotent(db_session):
    """Re-running the same extract should not create duplicate rows."""
    with _patch_provider_extract(SAMPLE_RECORDS):
        pipeline = ListingEventsPipeline(db_session)
        pipeline.run()

    with _patch_provider_extract(SAMPLE_RECORDS):
        # Build a fresh pipeline instance — the previous run already
        # committed; a second run should overwrite existing rows.
        pipeline = ListingEventsPipeline(db_session)
        result = pipeline.run()

    assert result.success is True
    rows = db_session.query(ListingEvent).all()
    assert len(rows) == 2  # unchanged count

    # Verify the upsert actually overwrote the stale value.
    co_a = db_session.query(ListingEvent).filter(ListingEvent.ts_code == "001289.SZ").first()
    assert co_a.name == "Co A"
    assert co_a.funds_raised is not None


def test_pipeline_upsert_overwrites_stale_values(db_session):
    """A second extract with modified fields should update existing rows."""
    with _patch_provider_extract(SAMPLE_RECORDS):
        ListingEventsPipeline(db_session).run()

    updated = [{**SAMPLE_RECORDS[0], "name": "Renamed Co A", "price": 99.0}]
    with _patch_provider_extract(updated):
        ListingEventsPipeline(db_session).run()

    co_a = db_session.query(ListingEvent).filter(ListingEvent.ts_code == "001289.SZ").first()
    assert co_a.name == "Renamed Co A"
    assert float(co_a.issue_price) == 99.0

    # Other rows untouched
    co_b = db_session.query(ListingEvent).filter(ListingEvent.ts_code == "688981.SH").first()
    assert co_b.name == "Co B"


def test_pipeline_extract_uses_default_date_window():
    """``extract()`` should call fetch_new_share with a YYYYMMDD window."""
    pipeline = ListingEventsPipeline.__new__(ListingEventsPipeline)
    pipeline.db = None

    with patch("app.data.pipelines.listing_events.TushareProvider") as provider_cls:
        provider_instance = provider_cls.return_value
        provider_instance.fetch_new_share.return_value = []
        records = pipeline.extract()

    assert records == []
    call_kwargs = provider_instance.fetch_new_share.call_args.kwargs
    assert "start_date" in call_kwargs
    assert "end_date" in call_kwargs
    assert len(call_kwargs["start_date"]) == 8 and len(call_kwargs["end_date"]) == 8


def test_pipeline_run_handles_empty_extract(db_session):
    """An empty extract list should return success=True with 0 records."""
    with _patch_provider_extract([]):
        pipeline = ListingEventsPipeline(db_session)
        result = pipeline.run()

    assert result.success is True
    assert result.records == 0
    assert db_session.query(ListingEvent).count() == 0


def test_pipeline_run_handles_partial_invalid_records(db_session):
    """Records missing ts_code or name should be filtered out, not crash."""
    bad_records = [
        {"ts_code": "", "name": "Empty Code"},  # missing ts_code
        {"ts_code": "600000.SH"},  # missing name
        SAMPLE_RECORDS[0],  # valid
    ]
    with _patch_provider_extract(bad_records):
        pipeline = ListingEventsPipeline(db_session)
        result = pipeline.run()

    assert result.success is True
    rows = db_session.query(ListingEvent).all()
    assert len(rows) == 1
    assert rows[0].ts_code == "001289.SZ"