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
        ),
        ETFInfo(
            code="510500",
            name="中证500ETF",
            market="A股",
            category="股票型",
            instrument_type="ETF",
            status="active",
        ),
        ETFInfo(
            code="BTC.US",
            name="Bitcoin",
            market="US",
            category="Layer1",
            instrument_type="CRYPTO",
            status="active",
        ),
        ETFInfo(
            code="ETH.US",
            name="Ethereum",
            market="US",
            category="Layer1",
            instrument_type="CRYPTO",
            status="active",
        ),
        ETFInfo(
            code="000001",
            name="平安银行",
            market="A股",
            category="银行",
            instrument_type="STOCK",
            status="active",
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
    assert set(categories) == {"股票型", "Layer1", "银行"}


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
