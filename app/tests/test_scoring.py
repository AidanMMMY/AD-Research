"""Tests for scoring models.

Covers creation and basic attribute validation of ScoreTemplate and ETFScore.
"""

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.scoring import ScoreTemplate, ETFScore, ReportMetadata
from app.models.etf import ETFInfo
from app.models.pool import ETFPools
from app.core.database import Base


@pytest.fixture(scope="module")
def db_session():
    """Create an in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_create_score_template(db_session):
    """ScoreTemplate should be created with correct attributes."""
    template = ScoreTemplate(
        name="Default Scoring",
        description="Default 5-dimension scoring template",
        weights={
            "return": 0.25,
            "risk": 0.20,
            "sharpe": 0.25,
            "liquidity": 0.15,
            "trend": 0.15,
        },
        is_default=True,
    )
    db_session.add(template)
    db_session.commit()

    assert template.id is not None
    assert template.name == "Default Scoring"
    assert template.is_default is True
    assert template.weights["sharpe"] == 0.25
    assert isinstance(template.created_at, datetime)


def test_create_etf_score(db_session):
    """ETFScore should be created with correct attributes and linked to ETF."""
    # Create prerequisite ETF
    etf = ETFInfo(
        code="510300",
        name="CSI 300 ETF",
        category="Equity",
    )
    db_session.add(etf)
    db_session.commit()

    # Create prerequisite template
    template = ScoreTemplate(
        name="Momentum Template",
        weights={"return": 0.4, "risk": 0.2, "sharpe": 0.2, "liquidity": 0.1, "trend": 0.1},
    )
    db_session.add(template)
    db_session.commit()

    score = ETFScore(
        etf_code="510300",
        trade_date=date(2024, 6, 1),
        template_id=template.id,
        composite_score=78.50,
        score_return=82.00,
        score_risk=75.00,
        score_sharpe=80.00,
        score_liquidity=70.00,
        score_trend=85.00,
        rank_overall=5,
        rank_category=2,
    )
    db_session.add(score)
    db_session.commit()

    assert score.id is not None
    assert score.etf_code == "510300"
    assert score.trade_date == date(2024, 6, 1)
    assert score.template_id == template.id
    assert float(score.composite_score) == 78.50
    assert float(score.score_sharpe) == 80.00
    assert score.rank_overall == 5
    assert score.rank_category == 2
    assert isinstance(score.created_at, datetime)


def test_create_report_metadata(db_session):
    """ReportMetadata should be created with correct attributes."""
    # Create prerequisite pool
    pool = ETFPools(name="Core Pool", description="Core ETF pool")
    db_session.add(pool)
    db_session.commit()

    # Create prerequisite template
    template = ScoreTemplate(
        name="Weekly Template",
        weights={"return": 0.3, "risk": 0.3, "sharpe": 0.2, "liquidity": 0.1, "trend": 0.1},
    )
    db_session.add(template)
    db_session.commit()

    report = ReportMetadata(
        report_type="weekly",
        report_date=date(2024, 6, 1),
        pool_id=pool.id,
        template_id=template.id,
        status="success",
        format="pdf",
        file_path="/reports/weekly_2024-06-01.pdf",
        file_size=102400,
    )
    db_session.add(report)
    db_session.commit()

    assert report.id is not None
    assert report.report_type == "weekly"
    assert report.status == "success"
    assert report.format == "pdf"
    assert report.file_path == "/reports/weekly_2024-06-01.pdf"
    assert report.file_size == 102400
    assert report.pool_id == pool.id
    assert report.template_id == template.id
    assert isinstance(report.created_at, datetime)
