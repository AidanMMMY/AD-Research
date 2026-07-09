"""Tests for ETFService."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.etf import ETFInfo
from app.services.etf_service import ETFService


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session_maker = sessionmaker(bind=engine)
    session = session_maker()
    yield session
    session.close()


@pytest.fixture
def sample_etfs(db_session):
    """Create sample ETFs spanning multiple markets and instrument types."""
    etfs = [
        ETFInfo(
            code="510300",
            name="沪深300ETF",
            market="A股",
            category="股票型",
            instrument_type="ETF",
            status="active",
            exchange="SH",
        ),
        ETFInfo(
            code="510500",
            name="中证500ETF",
            market="A股",
            category="股票型",
            instrument_type="ETF",
            status="active",
            exchange="SH",
        ),
        ETFInfo(
            code="BTC.US",
            name="Bitcoin",
            market="US",
            category="Layer1",
            instrument_type="CRYPTO",
            status="active",
            exchange="CRYPTO",
        ),
        ETFInfo(
            code="ETH.US",
            name="Ethereum",
            market="US",
            category="Layer1",
            instrument_type="CRYPTO",
            status="active",
            exchange="CRYPTO",
        ),
        ETFInfo(
            code="000001",
            name="平安银行",
            market="A股",
            category="银行",
            instrument_type="STOCK",
            status="active",
            exchange="SZ",
        ),
        ETFInfo(
            code="AAPL.US",
            name="Apple",
            market="US",
            category="Technology",
            instrument_type="STOCK",
            status="active",
            exchange="NASDAQ",
        ),
        ETFInfo(
            code="JPM.US",
            name="JPMorgan",
            market="US",
            category="Banks",
            instrument_type="STOCK",
            status="active",
            exchange="NYSE",
        ),
    ]
    for etf in etfs:
        db_session.add(etf)
    db_session.commit()
    return etfs


def test_get_categories_no_filter(db_session, sample_etfs):
    """get_categories without filters should return all non-empty categories."""
    service = ETFService(db_session)
    categories = service.get_categories()
    assert set(categories) == {"股票型", "Layer1", "银行", "Technology", "Banks"}


def test_get_categories_by_market(db_session, sample_etfs):
    """get_categories should filter by market."""
    service = ETFService(db_session)
    categories = service.get_categories(market="A股")
    assert set(categories) == {"股票型", "银行"}


def test_get_categories_by_instrument_type(db_session, sample_etfs):
    """get_categories should filter by instrument_type."""
    service = ETFService(db_session)
    categories = service.get_categories(instrument_type="CRYPTO")
    assert categories == ["Layer1"]


def test_get_categories_by_market_and_instrument_type(db_session, sample_etfs):
    """get_categories should support combined market and instrument_type filters."""
    service = ETFService(db_session)
    categories = service.get_categories(market="A股", instrument_type="STOCK")
    assert categories == ["银行"]


def test_get_categories_no_match(db_session, sample_etfs):
    """get_categories should return empty list when no records match filters."""
    service = ETFService(db_session)
    categories = service.get_categories(market="HK")
    assert categories == []


def test_get_categories_excludes_empty_strings(db_session, sample_etfs):
    """get_categories must drop empty-string rows so the frontend dropdown
    does not render a blank '无' option.

    Reproduces the 2026-07-08 分类 dropdown bug where rows with category=''
    (from incomplete ETL backfills) leaked into the facet list.
    """
    db_session.add(
        ETFInfo(
            code="999999",
            name="ghost",
            market="A股",
            category="",
            instrument_type="ETF",
            status="active",
        )
    )
    db_session.commit()
    service = ETFService(db_session)
    categories = service.get_categories(market="A股")
    assert "" not in categories
    assert "股票型" in categories


def test_get_categories_excludes_null_via_cascade(db_session, sample_etfs):
    """get_categories should respect cascade: when other filters narrow
    the result set, only categories that still produce rows are returned.
    """
    service = ETFService(db_session)
    # Add an ETF with a unique category that gets filtered out.
    db_session.add(
        ETFInfo(
            code="111111",
            name="only-stock-etf",
            market="A股",
            category="货币型",
            instrument_type="ETF",
            status="active",
        )
    )
    db_session.commit()
    # When type=STOCK, 货币型 should not appear (it belongs to an ETF).
    cats_stock = service.get_categories(market="A股", instrument_type="STOCK")
    assert "货币型" not in cats_stock
    assert "银行" in cats_stock


def test_exchange_filter_narrows_list(db_session, sample_etfs):
    """Filtering by exchange should only return rows on that exchange."""
    from app.schemas.etf import ETFFilterParams
    service = ETFService(db_session)
    params = ETFFilterParams(market="US", exchange="NYSE")
    response = service.list_etfs(params)
    codes = {item.code for item in response.items}
    assert codes == {"JPM.US"}
    assert response.total == 1


def test_get_categories_cascade_by_exchange(db_session, sample_etfs):
    """Category facet should only show categories present on the
    exchange-constrained result set."""
    from app.schemas.etf import ETFFilterParams
    service = ETFService(db_session)
    cats_nyse = service.get_categories(
        ETFFilterParams(market="US", exchange="NYSE")
    )
    assert "Banks" in cats_nyse
    assert "Technology" not in cats_nyse
    cats_nasdaq = service.get_categories(
        ETFFilterParams(market="US", exchange="NASDAQ")
    )
    assert "Technology" in cats_nasdaq
    assert "Banks" not in cats_nasdaq
