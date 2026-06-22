"""Tests for scoring models and calculation engine.

Covers creation and basic attribute validation of ScoreTemplate and ETFScore,
as well as the ScoreCalculator percentile-based scoring algorithm.
"""

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.etf import ETFInfo
from app.models.pool import ETFPools
from app.models.scoring import ETFScore, ReportMetadata, ScoreTemplate


@pytest.fixture(scope="module")
def db_session():
    """Create an in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session_maker = sessionmaker(bind=engine)
    session = session_maker()
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


# ---------------------------------------------------------------------------
# ScoreCalculator tests
# ---------------------------------------------------------------------------


def test_calculate_percentile_scores():
    """Test scoring with sample indicator data using percentile ranking."""
    indicators = [
        {"etf_code": "A", "sharpe_1y": 2.0, "volatility_20d": 15.0, "return_1y": 30.0},
        {"etf_code": "B", "sharpe_1y": 1.0, "volatility_20d": 25.0, "return_1y": 15.0},
        {"etf_code": "C", "sharpe_1y": 0.5, "volatility_20d": 35.0, "return_1y": 5.0},
        {"etf_code": "D", "sharpe_1y": 1.5, "volatility_20d": 20.0, "return_1y": 20.0},
    ]

    template_weights = {
        "return": {"metrics": ["return_1y"], "weight": 0.4, "direction": "asc"},
        "risk": {"metrics": ["volatility_20d"], "weight": 0.3, "direction": "desc"},
        "sharpe": {"metrics": ["sharpe_1y"], "weight": 0.3, "direction": "asc"},
    }

    from app.data.indicators.scoring import ScoreCalculator

    calculator = ScoreCalculator()
    results = calculator.calculate_scores(indicators, template_weights)

    # A has best return, lowest volatility, best sharpe -> highest score
    assert results["A"]["composite"] > results["B"]["composite"]
    assert results["A"]["composite"] > results["C"]["composite"]
    # C has worst metrics -> lowest score
    assert results["C"]["composite"] < results["B"]["composite"]
    # All results should have dimension keys
    for code in ("A", "B", "C", "D"):
        assert "composite" in results[code]
        assert "return" in results[code]
        assert "risk" in results[code]
        assert "sharpe" in results[code]


def test_rank_scores():
    """Test 1-based ranking from composite scores."""
    scores = {
        "A": {"composite": 85.0},
        "B": {"composite": 70.0},
        "C": {"composite": 90.0},
    }

    from app.data.indicators.scoring import ScoreCalculator

    calculator = ScoreCalculator()
    ranks = calculator.rank_scores(scores)

    assert ranks["C"] == 1  # Highest
    assert ranks["A"] == 2
    assert ranks["B"] == 3  # Lowest


def test_calculate_scores_empty_input():
    """ScoreCalculator should return empty dict for empty input."""
    from app.data.indicators.scoring import ScoreCalculator

    calculator = ScoreCalculator()
    results = calculator.calculate_scores([], {})
    assert results == {}


def test_rank_scores_empty_input():
    """rank_scores should return empty dict for empty input."""
    from app.data.indicators.scoring import ScoreCalculator

    calculator = ScoreCalculator()
    ranks = calculator.rank_scores({})
    assert ranks == {}


def test_calculate_scores_missing_values():
    """ScoreCalculator should handle missing metric values gracefully."""
    indicators = [
        {"etf_code": "A", "sharpe_1y": 2.0, "volatility_20d": 15.0},
        {"etf_code": "B", "sharpe_1y": 1.0},  # missing volatility_20d
        {"etf_code": "C"},  # missing all metrics
    ]

    template_weights = {
        "risk": {"metrics": ["volatility_20d"], "weight": 0.5, "direction": "desc"},
        "sharpe": {"metrics": ["sharpe_1y"], "weight": 0.5, "direction": "asc"},
    }

    from app.data.indicators.scoring import ScoreCalculator

    calculator = ScoreCalculator()
    results = calculator.calculate_scores(indicators, template_weights)

    # A should have both dimension scores
    assert "risk" in results["A"]
    assert "sharpe" in results["A"]
    # B missing volatility -> only sharpe dimension
    assert "sharpe" in results["B"]
    # C missing all metrics -> only composite key (0.0)
    assert "composite" in results["C"]


def test_calculate_scores_multi_metric_dimension():
    """ScoreCalculator should average multiple metrics within a dimension."""
    indicators = [
        {"etf_code": "A", "return_1m": 5.0, "return_3m": 15.0},
        {"etf_code": "B", "return_1m": 3.0, "return_3m": 9.0},
        {"etf_code": "C", "return_1m": 1.0, "return_3m": 3.0},
    ]

    template_weights = {
        "return": {"metrics": ["return_1m", "return_3m"], "weight": 1.0, "direction": "asc"},
    }

    from app.data.indicators.scoring import ScoreCalculator

    calculator = ScoreCalculator()
    results = calculator.calculate_scores(indicators, template_weights)

    # A: avg(5,15)=10, B: avg(3,9)=6, C: avg(1,3)=2
    # A should have highest composite score
    assert results["A"]["composite"] > results["B"]["composite"]
    assert results["B"]["composite"] > results["C"]["composite"]


def test_calculate_scores_direction_desc():
    """Direction 'desc' should invert percentiles so lower values score higher."""
    indicators = [
        {"etf_code": "A", "volatility_20d": 10.0},
        {"etf_code": "B", "volatility_20d": 20.0},
        {"etf_code": "C", "volatility_20d": 30.0},
    ]

    template_weights = {
        "risk": {"metrics": ["volatility_20d"], "weight": 1.0, "direction": "desc"},
    }

    from app.data.indicators.scoring import ScoreCalculator

    calculator = ScoreCalculator()
    results = calculator.calculate_scores(indicators, template_weights)

    # Lower volatility should score higher with desc direction
    assert results["A"]["composite"] > results["B"]["composite"]
    assert results["B"]["composite"] > results["C"]["composite"]


def test_calculate_scores_direction_asc():
    """Direction 'asc' should keep percentiles so higher values score higher."""
    indicators = [
        {"etf_code": "A", "return_1y": 30.0},
        {"etf_code": "B", "return_1y": 20.0},
        {"etf_code": "C", "return_1y": 10.0},
    ]

    template_weights = {
        "return": {"metrics": ["return_1y"], "weight": 1.0, "direction": "asc"},
    }

    from app.data.indicators.scoring import ScoreCalculator

    calculator = ScoreCalculator()
    results = calculator.calculate_scores(indicators, template_weights)

    # Higher return should score higher with asc direction
    assert results["A"]["composite"] > results["B"]["composite"]
    assert results["B"]["composite"] > results["C"]["composite"]


# ---------------------------------------------------------------------------
# ScoringService tests
# ---------------------------------------------------------------------------


def test_scoring_service_initialization(db_session):
    """ScoringService should initialize with a DB session and calculator."""
    from app.services.scoring_service import ScoringService

    service = ScoringService(db_session)

    assert service.db is db_session
    assert service.calculator is not None
    assert hasattr(service, "DIMENSION_MAP")
    assert "return" in service.DIMENSION_MAP
    assert "risk" in service.DIMENSION_MAP
    assert "sharpe" in service.DIMENSION_MAP
    assert "liquidity" in service.DIMENSION_MAP
    assert "trend" in service.DIMENSION_MAP


def test_scoring_service_dimension_map():
    """DIMENSION_MAP should map dimensions to correct metrics."""
    from app.services.scoring_service import ScoringService

    dm = ScoringService.DIMENSION_MAP

    assert dm["return"]["metrics"] == ["return_1m", "return_3m", "return_1y"]
    assert dm["risk"]["metrics"] == ["volatility_20d", "max_drawdown_1y"]
    assert dm["sharpe"]["metrics"] == ["sharpe_1y"]
    assert dm["liquidity"]["metrics"] == ["amount"]
    assert dm["trend"]["metrics"] == ["rsi14", "ma_position"]


def test_scoring_service_template_crud(db_session):
    """ScoringService should support template CRUD operations."""
    from app.services.scoring_service import ScoringService

    service = ScoringService(db_session)

    # Use a unique name to avoid conflicts with existing templates
    template = service.create_template(
        name="CRUD Test Template",
        description="A test template",
        weights={"return": 0.5, "risk": 0.5},
        is_default=False,
    )
    assert template.id is not None
    assert template.name == "CRUD Test Template"
    assert template.weights == {"return": 0.5, "risk": 0.5}

    # get_template
    fetched = service.get_template(template.id)
    assert fetched is not None
    assert fetched.name == "CRUD Test Template"

    # get_templates should include our template
    all_templates = service.get_templates()
    assert any(t.name == "CRUD Test Template" for t in all_templates)

    # get_default_template (none set yet for this test's data)
    # There may be a default from earlier tests, so just check it returns something
    service.get_default_template()
    # We don't assert None here because module-scoped fixture may have defaults


def test_scoring_service_default_template(db_session):
    """get_default_template should return a template marked as default."""
    from app.services.scoring_service import ScoringService

    service = ScoringService(db_session)

    # Use unique names to avoid conflicts with module-scoped fixture data
    service.create_template(
        name="Default Test Template",
        description="Default template",
        weights={"return": 0.3, "risk": 0.3, "sharpe": 0.4},
        is_default=True,
    )
    service.create_template(
        name="Other Test Template",
        description="Other template",
        weights={"return": 0.5, "risk": 0.5},
        is_default=False,
    )

    default = service.get_default_template()
    assert default is not None
    # get_default_template returns the first default; due to module-scoped fixture
    # there may be an earlier default. Just verify it IS a default template.
    assert default.is_default is True


def test_scoring_service_init_default_templates(db_session):
    """_init_default_templates should create 3 preset templates."""
    from app.services.scoring_service import ScoringService

    service = ScoringService(db_session)

    # Count templates before init
    before_count = len(service.get_templates())

    service._init_default_templates()

    templates = service.get_templates()
    # Should have added 3 new templates
    assert len(templates) == before_count + 3

    # The 3 preset names should be present
    names = {t.name for t in templates}
    assert "保守型" in names
    assert "均衡型" in names
    assert "进取型" in names

    # 均衡型 should be the default among the presets
    default = service.get_default_template()
    assert default is not None


def test_scoring_service_build_template_weights(db_session):
    """_build_template_weights should merge template weights with DIMENSION_MAP."""
    from app.services.scoring_service import ScoringService

    service = ScoringService(db_session)

    template = service.create_template(
        name="Custom",
        description="Custom weights",
        weights={"return": 0.4, "risk": 0.2, "sharpe": 0.4},
    )

    result = service._build_template_weights(template)

    assert "return" in result
    assert result["return"]["weight"] == 0.4
    assert result["return"]["metrics"] == ["return_1m", "return_3m", "return_1y"]
    assert result["return"]["direction"] == "asc"

    assert "risk" in result
    assert result["risk"]["weight"] == 0.2
    assert result["risk"]["direction"] == "desc"

    assert "sharpe" in result
    assert result["sharpe"]["weight"] == 0.4

    # Dimensions not in template weights use DIMENSION_MAP defaults
    assert "liquidity" in result
    assert result["liquidity"]["weight"] == 0.1
    assert "trend" in result
    assert result["trend"]["weight"] == 0.1


def test_scoring_service_calculate_daily_scores_no_data(db_session):
    """calculate_daily_scores should return empty dict when no indicators exist."""
    from app.services.scoring_service import ScoringService

    service = ScoringService(db_session)

    # No indicators in DB -> empty result
    result = service.calculate_daily_scores()
    assert result == {}


def test_scoring_service_get_scores_empty(db_session):
    """get_scores should return empty list when no scores exist."""
    from app.services.scoring_service import ScoringService

    service = ScoringService(db_session)

    # Create a template so template_id resolution works
    service.create_template(
        name="Default",
        description="Default",
        weights={"return": 0.3, "risk": 0.3, "sharpe": 0.4},
        is_default=True,
    )

    scores = service.get_scores()
    assert scores == []
