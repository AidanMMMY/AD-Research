"""Tests for USEtfDiscoveryPipeline."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.data.pipelines.us_etf_discovery import USEtfDiscoveryPipeline
from app.models.etf import ETFInfo


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session_maker = sessionmaker(bind=engine)
    session = session_maker()
    yield session
    session.close()


def test_us_etf_discovery_upserts_categories(db_session):
    """Pipeline should upsert US ETFs with category metadata."""
    # Pre-populate an existing US ETF with a missing category
    db_session.add(
        ETFInfo(
            code="SPY.US",
            name="Old Name",
            market="US",
            exchange="NYSE",
            category=None,
            currency="USD",
            instrument_type="ETF",
            status="active",
        )
    )
    db_session.commit()

    pipeline = USEtfDiscoveryPipeline(db_session)
    result = pipeline.run()

    assert result.success is True
    assert result.records > 0

    spy = db_session.query(ETFInfo).filter(ETFInfo.code == "SPY.US").first()
    assert spy is not None
    assert spy.category == "大盘"
    assert spy.name == "SPDR S&P 500 ETF Trust"
    assert spy.instrument_type == "ETF"
    assert spy.status == "active"


def test_us_etf_discovery_preserves_existing_data(db_session):
    """Pipeline should preserve existing price/indicator data while updating metadata."""
    db_session.add(
        ETFInfo(
            code="QQQ.US",
            name="QQQ",
            market="US",
            exchange="NASDAQ",
            category=None,
            currency="USD",
            instrument_type="ETF",
            status="active",
            fund_size=1000000.0,
        )
    )
    db_session.commit()

    pipeline = USEtfDiscoveryPipeline(db_session)
    result = pipeline.run()

    assert result.success is True

    qqq = db_session.query(ETFInfo).filter(ETFInfo.code == "QQQ.US").first()
    assert qqq.category == "大盘"
    assert qqq.fund_size == 1000000.0  # preserved
