"""Tests for the A-share ETF discovery & enrichment fix (B12).

Covers:
  * ``ETFMetadataEnrichmentPipeline.load`` upserts NEW rows from Tushare
    fund_basic (previously update-only — see issue B12).
  * Existing rows get Tushare metadata only when the DB column is empty.
  * Real ``category/manager/underlying_index`` values are never overwritten
    with ``None``.
  * ``ETFScannerService.scan_market`` does not overwrite a real
    ``category/manager/underlying_index`` with ``None`` from the akshare
    payload.
  * The Tushare ``fetch_etf_metadata`` mapping produces the platform
    vocabulary (``股票型/混合型/债券型/REITs/货币型/其他``).
"""

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.data.pipelines.etf_metadata_enrichment import ETFMetadataEnrichmentPipeline
from app.models.etf import ETFInfo
from app.services.etf_scanner_service import ETFScannerService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    """In-memory SQLite session for fast isolated tests."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine)
    session = Session_()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _tushare_payload(rows: list[dict]) -> pd.DataFrame:
    """Construct a fake Tushare fund_basic DataFrame in the format the
    provider would return after ``fetch_etf_metadata`` has renamed columns.
    """
    base_cols = [
        "code", "name", "manager", "category", "sub_category",
        "underlying_index", "inception_date", "list_date", "fund_size",
    ]
    df = pd.DataFrame(rows, columns=base_cols)
    return df


# ---------------------------------------------------------------------------
# Enrichment pipeline: insert new rows
# ---------------------------------------------------------------------------


def test_enrichment_inserts_new_etf(db_session):
    """ETFMetadataEnrichmentPipeline must insert ETFs that aren't yet in DB."""
    payload = _tushare_payload([{
        "code": "510050.SH",
        "name": "华夏上证50ETF",
        "manager": "华夏基金管理有限公司",
        "category": "股票型",
        "sub_category": None,
        "underlying_index": "上证50指数",
        "inception_date": date(2004, 12, 30),
        "list_date": date(2005, 2, 23),
        "fund_size": 600.0,
    }])

    with patch.object(
        ETFMetadataEnrichmentPipeline, "extract", return_value=payload
    ):
        pipeline = ETFMetadataEnrichmentPipeline(db_session)
        result = pipeline.run()

    assert result.success
    row = db_session.query(ETFInfo).filter(ETFInfo.code == "510050.SH").first()
    assert row is not None
    assert row.name == "华夏上证50ETF"
    assert row.category == "股票型"
    assert row.manager == "华夏基金管理有限公司"
    assert row.underlying_index == "上证50指数"
    assert row.exchange == "SH"
    assert row.market == "A股"
    assert row.instrument_type == "ETF"
    assert row.status == "active"


def test_enrichment_inserts_all_six_categories(db_session):
    """All six Tushare fund_type values should be present and preserved."""
    rows = [
        {"code": "510050.SH", "name": "股票型ETF",
         "manager": "M", "category": "股票型",
         "sub_category": None, "underlying_index": "idx",
         "inception_date": None, "list_date": None, "fund_size": None},
        {"code": "161039.SZ", "name": "混合型ETF", "manager": "M",
         "category": "混合型", "sub_category": None, "underlying_index": "idx",
         "inception_date": None, "list_date": None, "fund_size": None},
        {"code": "511010.SH", "name": "债券型ETF", "manager": "M",
         "category": "债券型", "sub_category": None, "underlying_index": "idx",
         "inception_date": None, "list_date": None, "fund_size": None},
        {"code": "511880.SH", "name": "货币型ETF", "manager": "M",
         "category": "货币型", "sub_category": None, "underlying_index": "idx",
         "inception_date": None, "list_date": None, "fund_size": None},
        {"code": "180101.SZ", "name": "REITs ETF", "manager": "M",
         "category": "REITs", "sub_category": None, "underlying_index": "idx",
         "inception_date": None, "list_date": None, "fund_size": None},
        {"code": "159001.SZ", "name": "其他ETF", "manager": "M",
         "category": "其他", "sub_category": None, "underlying_index": "idx",
         "inception_date": None, "list_date": None, "fund_size": None},
    ]
    payload = _tushare_payload(rows)

    with patch.object(
        ETFMetadataEnrichmentPipeline, "extract", return_value=payload
    ):
        pipeline = ETFMetadataEnrichmentPipeline(db_session)
        result = pipeline.run()

    assert result.success
    cats = sorted(
        {r.category for r in db_session.query(ETFInfo).all() if r.category}
    )
    assert cats == sorted(["股票型", "混合型", "债券型", "货币型", "REITs", "其他"])


# ---------------------------------------------------------------------------
# Enrichment pipeline: don't overwrite real values with None
# ---------------------------------------------------------------------------


def test_enrichment_does_not_overwrite_existing_category(db_session):
    """A pre-existing real category must be preserved when Tushare returns NaN."""
    db_session.add(
        ETFInfo(
            code="510050.SH",
            name="Existing Name",
            market="A股",
            exchange="SH",
            category="股票型",  # already curated
            manager="Existing Manager",
            underlying_index="Existing Index",
            instrument_type="ETF",
            status="active",
        )
    )
    db_session.commit()

    payload = _tushare_payload([{
        "code": "510050.SH",
        "name": "华夏上证50ETF",
        "manager": None,
        "category": None,
        "sub_category": None,
        "underlying_index": None,
        "inception_date": None,
        "list_date": None,
        "fund_size": None,
    }])

    with patch.object(
        ETFMetadataEnrichmentPipeline, "extract", return_value=payload
    ):
        pipeline = ETFMetadataEnrichmentPipeline(db_session)
        result = pipeline.run()

    assert result.success
    row = db_session.query(ETFInfo).filter(ETFInfo.code == "510050.SH").first()
    # Real values preserved.
    assert row.category == "股票型"
    assert row.manager == "Existing Manager"
    assert row.underlying_index == "Existing Index"
    # But the (non-null) name should still be applied since it was empty? No,
    # the existing name is also preserved. The Tushare row has None for
    # everything except code, so nothing is changed.
    assert row.name == "Existing Name"


def test_enrichment_fills_missing_fields_only(db_session):
    """For an existing row with empty manager/underlying_index, fill them."""
    db_session.add(
        ETFInfo(
            code="510300.SH",
            name="沪深300ETF",
            market="A股",
            exchange="SH",
            category="股票型",
            manager=None,
            underlying_index=None,
            instrument_type="ETF",
            status="active",
        )
    )
    db_session.commit()

    payload = _tushare_payload([{
        "code": "510300.SH",
        "name": "沪深300ETF",
        "manager": "华泰柏瑞基金管理有限公司",
        "category": "股票型",
        "sub_category": None,
        "underlying_index": "沪深300指数",
        "inception_date": date(2012, 5, 4),
        "list_date": date(2012, 5, 28),
        "fund_size": 1500.0,
    }])

    with patch.object(
        ETFMetadataEnrichmentPipeline, "extract", return_value=payload
    ):
        pipeline = ETFMetadataEnrichmentPipeline(db_session)
        result = pipeline.run()

    assert result.success
    row = db_session.query(ETFInfo).filter(ETFInfo.code == "510300.SH").first()
    assert row.manager == "华泰柏瑞基金管理有限公司"
    assert row.underlying_index == "沪深300指数"


def test_enrichment_skips_rows_with_no_name(db_session):
    """Rows missing a name must be skipped — a primary key without a name
    is unusable in the UI.
    """
    payload = _tushare_payload([{
        "code": "123456.SH",
        "name": None,
        "manager": "X",
        "category": "股票型",
        "sub_category": None,
        "underlying_index": "idx",
        "inception_date": None,
        "list_date": None,
        "fund_size": None,
    }])

    with patch.object(
        ETFMetadataEnrichmentPipeline, "extract", return_value=payload
    ):
        pipeline = ETFMetadataEnrichmentPipeline(db_session)
        result = pipeline.run()

    assert result.success
    # No row should be inserted.
    assert db_session.query(ETFInfo).count() == 0


# ---------------------------------------------------------------------------
# ETFScannerService: don't clobber real category with None
# ---------------------------------------------------------------------------


def _make_akshare_etf(code: str, name: str, **kwargs):
    """Construct a minimal ETFInfo dataclass mimicking akshare output.

    akshare returns None for category/manager/underlying_index.
    """
    from app.data.providers.base import ETFInfo as BaseETFInfo

    return BaseETFInfo(
        code=code,
        name=name,
        market="A股",
        exchange=kwargs.get("exchange", code.split(".")[-1]),
        category=kwargs.get("category"),
        manager=kwargs.get("manager"),
        underlying_index=kwargs.get("underlying_index"),
        instrument_type="ETF",
    )


def test_scanner_preserves_real_category(db_session):
    """The akshare scanner runs weekly.  It must not overwrite a curated
    category/manager/underlying_index with None.
    """
    db_session.add(
        ETFInfo(
            code="510050.SH",
            name="Old Name",
            market="A股",
            exchange="SH",
            category="股票型",  # curated
            manager="华夏基金",  # curated
            underlying_index="上证50指数",  # curated
            instrument_type="ETF",
            status="active",
        )
    )
    db_session.commit()

    fake_akshare_payload = [
        _make_akshare_etf("510050.SH", "New Name From Akshare"),
    ]

    with patch(
        "app.data.providers.akshare_provider.AkshareProvider.fetch_etf_list",
        return_value=fake_akshare_payload,
    ):
        service = ETFScannerService(db_session)
        result = service.scan_market()

    assert result["success"]
    row = db_session.query(ETFInfo).filter(ETFInfo.code == "510050.SH").first()
    # Name comes from akshare and is a real string.
    assert row.name == "New Name From Akshare"
    # Curated metadata preserved.
    assert row.category == "股票型"
    assert row.manager == "华夏基金"
    assert row.underlying_index == "上证50指数"


def test_scanner_fills_empty_category_from_akshare(db_session):
    """If the DB has no category and akshare has one, fill it in."""
    db_session.add(
        ETFInfo(
            code="510500.SH",
            name="中证500ETF",
            market="A股",
            exchange="SH",
            category=None,
            instrument_type="ETF",
            status="active",
        )
    )
    db_session.commit()

    fake_akshare_payload = [
        # Even though akshare normally returns None, in theory a new field
        # could appear.  We simulate that.
        _make_akshare_etf("510500.SH", "中证500ETF", category="股票型"),
    ]

    with patch(
        "app.data.providers.akshare_provider.AkshareProvider.fetch_etf_list",
        return_value=fake_akshare_payload,
    ):
        service = ETFScannerService(db_session)
        result = service.scan_market()

    assert result["success"]
    row = db_session.query(ETFInfo).filter(ETFInfo.code == "510500.SH").first()
    assert row.category == "股票型"


# ---------------------------------------------------------------------------
# Tushare provider: fetch_etf_metadata mapping
# ---------------------------------------------------------------------------


def test_tushare_fetch_etf_metadata_renames_columns():
    """``fetch_etf_metadata`` must rename Tushare columns to the platform
    vocabulary.  We mock the underlying ``_pro.fund_basic`` call so this
    test does not require network access.
    """
    from app.data.providers.tushare_provider import TushareProvider

    raw_df = pd.DataFrame([
        {
            "ts_code": "510050.SH",
            "name": "华夏上证50ETF",
            "management": "华夏基金管理有限公司",
            "fund_type": "股票型",
            "invest_type": None,
            "benchmark": "上证50指数",
            "found_date": "20041230",
            "list_date": "20050223",
            "issue_amount": 600.0,
        }
    ])

    fake_pro = type("P", (), {})()
    fake_pro.fund_basic = lambda **kwargs: raw_df

    with patch.object(TushareProvider, "__init__", lambda self: None):
        provider = TushareProvider.__new__(TushareProvider)
        provider._pro = fake_pro
        provider._limiter = type("L", (), {"acquire": lambda self: None})()

        result = provider.fetch_etf_metadata()

    assert not result.empty
    assert "code" in result.columns
    assert result.iloc[0]["code"] == "510050.SH"
    assert result.iloc[0]["category"] == "股票型"
    assert result.iloc[0]["manager"] == "华夏基金管理有限公司"
    assert result.iloc[0]["underlying_index"] == "上证50指数"
