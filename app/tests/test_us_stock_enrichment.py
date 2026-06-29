"""Tests for USStockEnrichmentPipeline."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.data.pipelines.us_stock_enrichment import USStockEnrichmentPipeline
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


def _mock_csv_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Symbol": "AAPL", "Security": "Apple Inc.", "GICS Sector": "Technology", "GICS Sub-Industry": "Consumer Electronics"},
            {"Symbol": "MSFT", "Security": "Microsoft", "GICS Sector": "Technology", "GICS Sub-Industry": "Systems Software"},
        ]
    )


def test_enrichment_populates_missing_category_and_sector(db_session):
    """Pipeline should fill missing sector/industry/category from CSV."""
    db_session.add(
        ETFInfo(
            code="AAPL.US",
            name="Apple",
            market="US",
            instrument_type="STOCK",
            sector=None,
            industry=None,
            category=None,
            status="active",
        )
    )
    db_session.commit()

    pipeline = USStockEnrichmentPipeline(db_session)
    with patch(
        "app.data.pipelines.us_stock_enrichment.pd.read_csv",
        return_value=_mock_csv_df(),
    ):
        with patch(
            "app.data.pipelines.us_stock_enrichment.requests.get",
            return_value=MagicMock(text="csv", raise_for_status=MagicMock()),
        ):
            result = pipeline.run()

    assert result.success is True
    assert result.records == 1

    aapl = db_session.query(ETFInfo).filter(ETFInfo.code == "AAPL.US").first()
    assert aapl.sector == "Technology"
    assert aapl.industry == "Consumer Electronics"
    assert aapl.category == "Technology"


def test_enrichment_skips_stocks_with_existing_category(db_session):
    """Pipeline should not overwrite existing category data."""
    db_session.add(
        ETFInfo(
            code="MSFT.US",
            name="Microsoft",
            market="US",
            instrument_type="STOCK",
            sector="Technology",
            industry="Software",
            category="Technology",
            status="active",
        )
    )
    db_session.commit()

    pipeline = USStockEnrichmentPipeline(db_session)
    with patch(
        "app.data.pipelines.us_stock_enrichment.pd.read_csv",
        return_value=_mock_csv_df(),
    ):
        with patch(
            "app.data.pipelines.us_stock_enrichment.requests.get",
            return_value=MagicMock(text="csv", raise_for_status=MagicMock()),
        ):
            result = pipeline.run()

    assert result.success is True
    assert result.records == 0

    msft = db_session.query(ETFInfo).filter(ETFInfo.code == "MSFT.US").first()
    assert msft.category == "Technology"


def test_enrichment_ignores_tickers_not_in_csv(db_session):
    """Stocks not present in the CSV should be skipped without failing."""
    db_session.add(
        ETFInfo(
            code="UNKNOWN.US",
            name="Unknown",
            market="US",
            instrument_type="STOCK",
            sector=None,
            category=None,
            status="active",
        )
    )
    db_session.commit()

    pipeline = USStockEnrichmentPipeline(db_session)
    with patch(
        "app.data.pipelines.us_stock_enrichment.pd.read_csv",
        return_value=_mock_csv_df(),
    ):
        with patch(
            "app.data.pipelines.us_stock_enrichment.requests.get",
            return_value=MagicMock(text="csv", raise_for_status=MagicMock()),
        ):
            result = pipeline.run()

    assert result.success is True
    assert result.records == 0
