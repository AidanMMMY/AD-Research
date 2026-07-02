"""Tests for the futures ETL pipelines.

Focuses on:
- ``_symbol_root`` extracts alphabetic root from continuous contract codes.
- ``_classify_product`` maps (exchange, symbol_root) to product category.
- ``_coerce_date`` / ``_coerce_int`` / ``_coerce_float`` helpers.
- ``FuturesContractDiscoveryPipeline`` upserts sina's main contract list
  correctly, including product classification.
- ``FuturesDailyPipeline`` extracts, transforms and loads daily bars from
  akshare into the DB (mocked), with cache invalidation.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pandas as pd
import pytest

from app.data.pipelines.futures import (
    FuturesContractDiscoveryPipeline,
    FuturesDailyPipeline,
    _classify_product,
    _coerce_date,
    _coerce_float,
    _coerce_int,
    _symbol_root,
)
from app.models.futures import FuturesContract, FuturesDailyBar


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestSymbolRoot:
    @pytest.mark.parametrize("symbol,expected", [
        ("CU0", "CU"),
        ("M0", "M"),
        ("IF0", "IF"),
        ("AU2506", "AU"),
        ("TA2509", "TA"),
        ("PTA2606", "PTA"),
        ("V2606", "V"),
    ])
    def test_extracts_alphabetic_prefix(self, symbol, expected):
        assert _symbol_root(symbol) == expected


class TestClassifyProduct:
    @pytest.mark.parametrize("exchange,symbol_root,expected", [
        ("SHFE", "CU", "金属"),
        ("DCE", "M", "农产品"),
        ("CZCE", "SR", "农产品"),
        ("CFFEX", "IF", "金融期货"),
        ("INE", "SC", "能源化工"),
        ("GFEX", "SI", "金属"),
        ("SHFE", "UNKNOWN", "其他"),  # falls back
    ])
    def test_classifies_by_exchange_and_root(self, exchange, symbol_root, expected):
        assert _classify_product(exchange, symbol_root) == expected


class TestCoerceDate:
    @pytest.mark.parametrize("value,expected", [
        ("2026-07-01", date(2026, 7, 1)),
        ("2026/07/01", date(2026, 7, 1)),
        (date(2026, 7, 1), date(2026, 7, 1)),
        (None, None),
    ])
    def test_parses_supported_formats(self, value, expected):
        assert _coerce_date(value) == expected

    def test_returns_none_for_unparseable(self):
        assert _coerce_date("not-a-date") is None


class TestCoerceInt:
    def test_int_passthrough(self):
        assert _coerce_int(42) == 42

    def test_float_string(self):
        assert _coerce_int("100") == 100

    def test_nan_returns_none(self):
        assert _coerce_int(float("nan")) is None

    def test_none_returns_none(self):
        assert _coerce_int(None) is None

    def test_invalid_string_returns_none(self):
        assert _coerce_int("not-a-number") is None


class TestCoerceFloat:
    def test_float_passthrough(self):
        assert _coerce_float(3.14) == 3.14

    def test_int_to_float(self):
        assert _coerce_float(5) == 5.0

    def test_string(self):
        assert _coerce_float("1.23") == 1.23

    def test_nan_returns_none(self):
        assert _coerce_float(float("nan")) is None

    def test_none_returns_none(self):
        assert _coerce_float(None) is None


# ---------------------------------------------------------------------------
# Contract discovery pipeline
# ---------------------------------------------------------------------------


SAMPLE_SINA_DF = pd.DataFrame(
    [
        {"symbol": "CU0", "exchange": "shfe", "name": "沪铜主力"},
        {"symbol": "AU0", "exchange": "shfe", "name": "黄金主力"},
        {"symbol": "M0", "exchange": "dce", "name": "豆粕主力"},
        {"symbol": "IF0", "exchange": "cffex", "name": "沪深300"},
        # Filtered: empty fields
        {"symbol": "", "exchange": "shfe", "name": "X"},
        # Filtered: unknown exchange
        {"symbol": "Z0", "exchange": "unknown_ex", "name": "X"},
    ]
)


def _patch_futures_display_main_sina(df: pd.DataFrame):
    """Patch the sina main-contract discovery endpoint."""
    return patch(
        "app.data.pipelines.futures.ak.futures_display_main_sina",
        return_value=df,
    )


def test_discovery_pipeline_extracts_only_valid_rows(db_session):
    with _patch_futures_display_main_sina(SAMPLE_SINA_DF):
        pipeline = FuturesContractDiscoveryPipeline(db_session)
        rows = pipeline.extract()
    # 4 valid (skip empty symbol + unknown exchange)
    assert len(rows) == 4
    codes = set(rows["code"].tolist())
    assert codes == {"CU0", "AU0", "M0", "IF0"}


def test_discovery_pipeline_classifies_products(db_session):
    with _patch_futures_display_main_sina(SAMPLE_SINA_DF):
        pipeline = FuturesContractDiscoveryPipeline(db_session)
        rows = pipeline.extract()

    by_code = {r["code"]: r for _, r in rows.iterrows()}
    assert by_code["CU0"]["product"] == "金属"
    assert by_code["M0"]["product"] == "农产品"
    assert by_code["IF0"]["product"] == "金融期货"


def test_discovery_pipeline_load_writes_rows(db_session):
    with _patch_futures_display_main_sina(SAMPLE_SINA_DF):
        pipeline = FuturesContractDiscoveryPipeline(db_session)
        df = pipeline.extract()
        n = pipeline.load(df)

    assert n == 4
    rows = db_session.query(FuturesContract).all()
    assert len(rows) == 4


def test_discovery_pipeline_is_idempotent(db_session):
    with _patch_futures_display_main_sina(SAMPLE_SINA_DF):
        pipeline = FuturesContractDiscoveryPipeline(db_session)
        pipeline.load(pipeline.extract())

    with _patch_futures_display_main_sina(SAMPLE_SINA_DF):
        pipeline2 = FuturesContractDiscoveryPipeline(db_session)
        pipeline2.load(pipeline2.extract())

    # Upsert on `code` keeps row count at 4
    assert db_session.query(FuturesContract).count() == 4


def test_discovery_pipeline_handles_empty_response(db_session):
    with _patch_futures_display_main_sina(pd.DataFrame()):
        pipeline = FuturesContractDiscoveryPipeline(db_session)
        df = pipeline.extract()
        n = pipeline.load(df)
    assert df.empty
    assert n == 0


def test_discovery_pipeline_handles_akshare_exception(db_session):
    """If akshare raises, extract returns an empty DataFrame (no crash)."""
    with patch(
        "app.data.pipelines.futures.ak.futures_display_main_sina",
        side_effect=Exception("network error"),
    ):
        pipeline = FuturesContractDiscoveryPipeline(db_session)
        df = pipeline.extract()
        n = pipeline.load(df)
    assert df.empty
    assert n == 0


# ---------------------------------------------------------------------------
# Daily bar pipeline
# ---------------------------------------------------------------------------


def _make_daily_df(rows):
    """Create a sina-style daily DataFrame with Chinese column headers."""
    return pd.DataFrame(
        rows,
        columns=[
            "日期",
            "开盘价",
            "最高价",
            "最低价",
            "收盘价",
            "成交量",
            "持仓量",
            "动态结算价",
        ],
    )


def test_daily_pipeline_extract_normalizes_chinese_columns(db_session):
    db_session.add(
        FuturesContract(
            code="CU0",
            name="沪铜主力",
            exchange="SHFE",
            product="金属",
            is_main=True,
        )
    )
    db_session.commit()

    df = _make_daily_df(
        [
            ("2026-06-30", 100.0, 102.0, 99.0, 101.0, 1000, 2000, 100.5),
            ("2026-07-01", 101.0, 103.0, 100.0, 102.0, 1500, 2500, 101.5),
        ]
    )

    with patch(
        "app.data.pipelines.futures.ak.futures_main_sina", return_value=df
    ):
        pipeline = FuturesDailyPipeline(db_session)
        out = pipeline.extract()

    assert len(out) == 2
    assert "settle" in out.columns
    assert "pre_settle" in out.columns
    # pre_settle for the latest row = previous day's settle
    latest = out.sort_values("trade_date").iloc[-1]
    assert float(latest["settle"]) == 101.5
    assert float(latest["pre_settle"]) == 100.5


def test_daily_pipeline_extract_respects_history_window(db_session):
    db_session.add(
        FuturesContract(
            code="CU0",
            name="沪铜主力",
            exchange="SHFE",
            product="金属",
            is_main=True,
        )
    )
    db_session.commit()

    rows = []
    for d in range(20):
        iso = (date(2026, 6, 1) - __import__("datetime").timedelta(days=d)).isoformat()
        rows.append((iso, 100.0, 102.0, 99.0, 101.0, 1000, 2000, 100.5))
    df = _make_daily_df(list(reversed(rows)))

    with patch(
        "app.data.pipelines.futures.ak.futures_main_sina", return_value=df
    ):
        # history_days=5 → only keep last 5 days
        pipeline = FuturesDailyPipeline(db_session, history_days=5, target_date=date(2026, 6, 1))
        out = pipeline.extract()

    # 5 days kept (target_date included)
    assert len(out) == 5


def test_daily_pipeline_extract_skips_when_no_contracts(db_session):
    pipeline = FuturesDailyPipeline(db_session)
    df = pipeline.extract()
    assert df.empty


def test_daily_pipeline_load_writes_and_invalidates_cache(db_session):
    db_session.add(
        FuturesContract(
            code="CU0",
            name="沪铜主力",
            exchange="SHFE",
            product="金属",
            is_main=True,
        )
    )
    db_session.commit()

    df = _make_daily_df(
        [("2026-07-01", 101.0, 103.0, 100.0, 102.0, 1500, 2500, 101.5)]
    )

    with patch(
        "app.data.pipelines.futures.ak.futures_main_sina", return_value=df
    ), patch(
        "app.data.pipelines.futures.cache_invalidate_pattern", return_value=0
    ) as mock_invalidate:
        pipeline = FuturesDailyPipeline(db_session)
        extracted = pipeline.extract()
        n = pipeline.load(extracted)

    assert n == 1
    bar = db_session.query(FuturesDailyBar).filter_by(code="CU0").first()
    assert bar is not None
    assert bar.trade_date == date(2026, 7, 1)
    assert bar.settle == Decimal("101.5000")
    assert bar.volume == 1500
    # Cache invalidated with the futures:* pattern
    mock_invalidate.assert_called_once()
    assert "futures:" in str(mock_invalidate.call_args)


def test_daily_pipeline_load_is_upsert(db_session):
    """Re-running with same (code, date) should not duplicate rows."""
    db_session.add(
        FuturesContract(
            code="CU0",
            name="沪铜主力",
            exchange="SHFE",
            product="金属",
            is_main=True,
        )
    )
    db_session.commit()

    df = _make_daily_df(
        [("2026-07-01", 101.0, 103.0, 100.0, 102.0, 1500, 2500, 101.5)]
    )

    with patch(
        "app.data.pipelines.futures.ak.futures_main_sina", return_value=df
    ), patch("app.data.pipelines.futures.cache_invalidate_pattern", return_value=0):
        pipeline = FuturesDailyPipeline(db_session)
        pipeline.load(pipeline.extract())

    with patch(
        "app.data.pipelines.futures.ak.futures_main_sina", return_value=df
    ), patch("app.data.pipelines.futures.cache_invalidate_pattern", return_value=0):
        pipeline = FuturesDailyPipeline(db_session)
        pipeline.load(pipeline.extract())

    assert db_session.query(FuturesDailyBar).count() == 1


def test_daily_pipeline_extract_handles_akshare_failure(db_session):
    """If akshare returns empty for a contract, the pipeline continues."""
    db_session.add(
        FuturesContract(
            code="CU0",
            name="沪铜主力",
            exchange="SHFE",
            product="金属",
            is_main=True,
        )
    )
    db_session.commit()

    with patch(
        "app.data.pipelines.futures.ak.futures_main_sina", return_value=pd.DataFrame()
    ):
        pipeline = FuturesDailyPipeline(db_session)
        out = pipeline.extract()
    assert out.empty
