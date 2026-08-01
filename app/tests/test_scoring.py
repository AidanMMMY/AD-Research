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
    # Volatility and return are now stored as decimals (0.15 ≈ 15%).
    indicators = [
        {"etf_code": "A", "sharpe_1y": 2.0, "volatility_20d": 0.15, "return_1y": 0.30},
        {"etf_code": "B", "sharpe_1y": 1.0, "volatility_20d": 0.25, "return_1y": 0.15},
        {"etf_code": "C", "sharpe_1y": 0.5, "volatility_20d": 0.35, "return_1y": 0.05},
        {"etf_code": "D", "sharpe_1y": 1.5, "volatility_20d": 0.20, "return_1y": 0.20},
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
        {"etf_code": "A", "sharpe_1y": 2.0, "volatility_20d": 0.15},
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
        {"etf_code": "A", "return_1m": 0.05, "return_3m": 0.15},
        {"etf_code": "B", "return_1m": 0.03, "return_3m": 0.09},
        {"etf_code": "C", "return_1m": 0.01, "return_3m": 0.03},
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
        {"etf_code": "A", "volatility_20d": 0.10},
        {"etf_code": "B", "volatility_20d": 0.20},
        {"etf_code": "C", "volatility_20d": 0.30},
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
        {"etf_code": "A", "return_1y": 0.30},
        {"etf_code": "B", "return_1y": 0.20},
        {"etf_code": "C", "return_1y": 0.10},
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


def test_get_scores_uses_latest_date_per_market(db_session):
    """Lagging markets must still appear when another market advanced.

    Regression test: get_scores previously resolved a single global
    max(trade_date), so once US scores moved to a newer date the A股
    rows (one trading day behind) disappeared from the ranking.
    """
    from app.services.scoring_service import ScoringService

    service = ScoringService(db_session)

    template = service.create_template(
        name="Per-Market Latest",
        description="regression",
        weights={"return": 0.3, "risk": 0.3, "sharpe": 0.4},
    )

    db_session.add_all(
        [
            ETFInfo(code="TST_A1", name="A Share Fund", market="A股", category="Equity"),
            ETFInfo(code="TST_US1", name="US Stock", market="US", category="Equity"),
        ]
    )
    db_session.commit()

    db_session.add_all(
        [
            ETFScore(
                etf_code="TST_A1",
                trade_date=date(2024, 7, 29),
                template_id=template.id,
                composite_score=60,
                rank_overall=1,
            ),
            ETFScore(
                etf_code="TST_US1",
                trade_date=date(2024, 7, 29),
                template_id=template.id,
                composite_score=50,
                rank_overall=2,
            ),
            # US advances one day; A股 has no score for the newer date yet.
            ETFScore(
                etf_code="TST_US1",
                trade_date=date(2024, 7, 30),
                template_id=template.id,
                composite_score=70,
                rank_overall=1,
            ),
        ]
    )
    db_session.commit()

    scores = service.get_scores(template_id=template.id)
    by_code = {s["etf_code"]: s for s in scores}
    assert set(by_code) == {"TST_A1", "TST_US1"}
    assert by_code["TST_A1"]["trade_date"] == date(2024, 7, 29)
    assert by_code["TST_US1"]["trade_date"] == date(2024, 7, 30)
    assert service.count_scores(template_id=template.id) == 2

    # Explicit date filtering still narrows to a single date.
    only_us = service.get_scores(template_id=template.id, trade_date=date(2024, 7, 30))
    assert {s["etf_code"] for s in only_us} == {"TST_US1"}
    assert service.count_scores(template_id=template.id, trade_date=date(2024, 7, 30)) == 1


def _seed_ranking_filter_fixture(db_session, service):
    """Seed one A股 ETF, one US stock, one US ETF and one crypto score row.

    Returns the template. Codes use the ``FLT_`` prefix so they never
    collide with other tests sharing the module-scoped session, and the
    seeding is idempotent because that session persists across tests in
    this module.
    """
    existing = (
        db_session.query(ScoreTemplate)
        .filter(ScoreTemplate.name == "Ranking Filters")
        .first()
    )
    if existing is not None:
        return existing

    template = service.create_template(
        name="Ranking Filters",
        description="filter tests",
        weights={"return": 0.3, "risk": 0.3, "sharpe": 0.4},
    )
    trade_date = date(2024, 8, 1)

    db_session.add_all(
        [
            ETFInfo(
                code="FLT_CN_ETF",
                name="CN ETF",
                market="A股",
                category="Equity",
                instrument_type="ETF",
            ),
            ETFInfo(
                code="FLT_US_STOCK",
                name="US Stock",
                market="US",
                category="Equity",
                instrument_type="STOCK",
            ),
            ETFInfo(
                code="FLT_US_ETF",
                name="US ETF",
                market="US",
                category="Equity",
                instrument_type="ETF",
            ),
            # Legacy-style row: NULL instrument_type counts as ETF.
            ETFInfo(
                code="FLT_CN_LEGACY",
                name="CN Legacy ETF",
                market="A股",
                category="Equity",
                instrument_type=None,
            ),
            ETFInfo(
                code="FLT_CRYPTO",
                name="Crypto Pair",
                market="CRYPTO",
                category="Crypto",
                instrument_type="CRYPTO",
            ),
        ]
    )
    db_session.commit()

    db_session.add_all(
        [
            ETFScore(
                etf_code=code,
                trade_date=trade_date,
                template_id=template.id,
                composite_score=score,
                rank_overall=rank,
            )
            for rank, (code, score) in enumerate(
                [
                    ("FLT_CN_ETF", 90),
                    ("FLT_US_STOCK", 80),
                    ("FLT_US_ETF", 70),
                    ("FLT_CN_LEGACY", 60),
                    ("FLT_CRYPTO", 50),
                ],
                start=1,
            )
        ]
    )
    db_session.commit()
    return template


def test_get_scores_excludes_crypto_by_default(db_session):
    """Crypto rows (暂不纳入数字币) never appear in the ranking query."""
    from app.services.scoring_service import ScoringService

    service = ScoringService(db_session)
    template = _seed_ranking_filter_fixture(db_session, service)

    scores = service.get_scores(template_id=template.id)
    codes = {s["etf_code"] for s in scores}
    assert "FLT_CRYPTO" not in codes
    assert codes == {"FLT_CN_ETF", "FLT_US_STOCK", "FLT_US_ETF", "FLT_CN_LEGACY"}
    assert service.count_scores(template_id=template.id) == 4

    # Explicit trade_date keeps the crypto exclusion too.
    dated = service.get_scores(template_id=template.id, trade_date=date(2024, 8, 1))
    assert "FLT_CRYPTO" not in {s["etf_code"] for s in dated}
    assert service.count_scores(template_id=template.id, trade_date=date(2024, 8, 1)) == 4


def test_get_scores_market_alias_filters(db_session):
    """Short market codes cn_a / us map to the DB values A股 / US."""
    from app.services.scoring_service import ScoringService

    service = ScoringService(db_session)
    template = _seed_ranking_filter_fixture(db_session, service)

    cn = service.get_scores(template_id=template.id, market="cn_a")
    assert {s["etf_code"] for s in cn} == {"FLT_CN_ETF", "FLT_CN_LEGACY"}
    assert service.count_scores(template_id=template.id, market="cn_a") == 2

    us = service.get_scores(template_id=template.id, market="us")
    assert {s["etf_code"] for s in us} == {"FLT_US_STOCK", "FLT_US_ETF"}
    assert service.count_scores(template_id=template.id, market="us") == 2

    # Raw DB values keep working (back-compat).
    raw = service.get_scores(template_id=template.id, market="A股")
    assert {s["etf_code"] for s in raw} == {"FLT_CN_ETF", "FLT_CN_LEGACY"}


def test_get_scores_instrument_type_filters(db_session):
    """instrument_type=ETF/STOCK narrows the ranking; NULL counts as ETF."""
    from app.services.scoring_service import ScoringService

    service = ScoringService(db_session)
    template = _seed_ranking_filter_fixture(db_session, service)

    etfs = service.get_scores(template_id=template.id, instrument_type="ETF")
    assert {s["etf_code"] for s in etfs} == {"FLT_CN_ETF", "FLT_US_ETF", "FLT_CN_LEGACY"}
    assert service.count_scores(template_id=template.id, instrument_type="ETF") == 3

    stocks = service.get_scores(template_id=template.id, instrument_type="stock")
    assert {s["etf_code"] for s in stocks} == {"FLT_US_STOCK"}
    assert service.count_scores(template_id=template.id, instrument_type="STOCK") == 1

    # Combined market + type filter.
    us_etfs = service.get_scores(
        template_id=template.id, market="us", instrument_type="ETF"
    )
    assert {s["etf_code"] for s in us_etfs} == {"FLT_US_ETF"}


def test_get_scores_per_market_latest_unaffected_by_crypto(db_session):
    """A crypto market bucket must not shift per-market latest-date joins."""
    from app.services.scoring_service import ScoringService

    service = ScoringService(db_session)
    template = service.create_template(
        name="Crypto Latest Date",
        description="regression",
        weights={"return": 0.3, "risk": 0.3, "sharpe": 0.4},
    )

    db_session.add_all(
        [
            ETFInfo(
                code="FLT2_US",
                name="US ETF 2",
                market="US",
                category="Equity",
                instrument_type="ETF",
            ),
            ETFInfo(
                code="FLT2_CRYPTO",
                name="Crypto 2",
                market="CRYPTO",
                category="Crypto",
                instrument_type="CRYPTO",
            ),
        ]
    )
    db_session.commit()
    db_session.add_all(
        [
            ETFScore(
                etf_code="FLT2_US",
                trade_date=date(2024, 8, 1),
                template_id=template.id,
                composite_score=70,
                rank_overall=1,
            ),
            # Crypto has a NEWER scored date than US — the ranking must
            # still return the US row at its own latest date.
            ETFScore(
                etf_code="FLT2_CRYPTO",
                trade_date=date(2024, 8, 2),
                template_id=template.id,
                composite_score=99,
                rank_overall=1,
            ),
        ]
    )
    db_session.commit()

    scores = service.get_scores(template_id=template.id)
    assert {s["etf_code"] for s in scores} == {"FLT2_US"}
    assert scores[0]["trade_date"] == date(2024, 8, 1)
    assert service.count_scores(template_id=template.id) == 1


def _seed_display_rank_fixture(db_session, service):
    """Seed scores whose stored ranks interleave crypto rows.

    Stored ``rank_overall`` is whole-market (crypto included), so after
    the ranking query excludes crypto the raw sequence has holes:
    1, 3, 5. Codes use the ``RNK_`` prefix and the seeding is idempotent
    (module-scoped session).
    """
    existing = (
        db_session.query(ScoreTemplate)
        .filter(ScoreTemplate.name == "Display Rank Renumber")
        .first()
    )
    if existing is not None:
        return existing

    template = service.create_template(
        name="Display Rank Renumber",
        description="display rank tests",
        weights={"return": 0.3, "risk": 0.3, "sharpe": 0.4},
    )
    trade_date = date(2024, 8, 1)

    db_session.add_all(
        [
            ETFInfo(
                code="RNK_CN_A",
                name="CN A",
                market="A股",
                category="Equity",
                instrument_type="ETF",
            ),
            ETFInfo(
                code="RNK_US",
                name="US ETF",
                market="US",
                category="Equity",
                instrument_type="ETF",
            ),
            ETFInfo(
                code="RNK_CN_B",
                name="CN B",
                market="A股",
                category="Equity",
                instrument_type="ETF",
            ),
            ETFInfo(
                code="RNK_CRYPTO_A",
                name="Crypto A",
                market="CRYPTO",
                category="Crypto",
                instrument_type="CRYPTO",
            ),
            ETFInfo(
                code="RNK_CRYPTO_B",
                name="Crypto B",
                market="CRYPTO",
                category="Crypto",
                instrument_type="CRYPTO",
            ),
        ]
    )
    db_session.commit()

    db_session.add_all(
        [
            ETFScore(
                etf_code=code,
                trade_date=trade_date,
                template_id=template.id,
                composite_score=score,
                rank_overall=rank,
            )
            for rank, (code, score) in enumerate(
                [
                    ("RNK_CN_A", 90),
                    ("RNK_CRYPTO_A", 85),
                    ("RNK_US", 80),
                    ("RNK_CRYPTO_B", 75),
                    ("RNK_CN_B", 70),
                ],
                start=1,
            )
        ]
    )
    db_session.commit()
    return template


def test_get_scores_display_rank_continuous_after_crypto_exclusion(db_session):
    """rank_overall is re-numbered 1..N; the stored rank is preserved."""
    from app.services.scoring_service import ScoringService

    service = ScoringService(db_session)
    template = _seed_display_rank_fixture(db_session, service)

    scores = service.get_scores(template_id=template.id)
    codes = [s["etf_code"] for s in scores]
    # Stored ranks were 1/3/5 (crypto held 2 and 4) — order is kept,
    # display ranks become continuous.
    assert codes == ["RNK_CN_A", "RNK_US", "RNK_CN_B"]
    assert [s["rank_overall"] for s in scores] == [1, 2, 3]
    assert [s["rank_overall_original"] for s in scores] == [1, 3, 5]


def test_get_scores_display_rank_continuous_with_market_filter(db_session):
    """Market / instrument filters also yield a continuous 1..N display rank."""
    from app.services.scoring_service import ScoringService

    service = ScoringService(db_session)
    template = _seed_display_rank_fixture(db_session, service)

    cn = service.get_scores(template_id=template.id, market="cn_a")
    assert [s["etf_code"] for s in cn] == ["RNK_CN_A", "RNK_CN_B"]
    assert [s["rank_overall"] for s in cn] == [1, 2]
    assert [s["rank_overall_original"] for s in cn] == [1, 5]

    us = service.get_scores(template_id=template.id, market="us")
    assert [s["etf_code"] for s in us] == ["RNK_US"]
    assert [s["rank_overall"] for s in us] == [1]
    assert us[0]["rank_overall_original"] == 3

    etfs = service.get_scores(template_id=template.id, instrument_type="ETF")
    assert [s["rank_overall"] for s in etfs] == list(range(1, len(etfs) + 1))


def test_get_scores_display_rank_continuous_with_limit(db_session):
    """A truncated page still gets a continuous 1..limit display rank."""
    from app.services.scoring_service import ScoringService

    service = ScoringService(db_session)
    template = _seed_display_rank_fixture(db_session, service)

    top2 = service.get_scores(template_id=template.id, limit=2)
    assert [s["etf_code"] for s in top2] == ["RNK_CN_A", "RNK_US"]
    assert [s["rank_overall"] for s in top2] == [1, 2]
    assert [s["rank_overall_original"] for s in top2] == [1, 3]


def test_get_scores_ranking_filters_fixture_display_rank(db_session):
    """Existing FLT_ fixture (crypto ranked last) stays 1..N with originals."""
    from app.services.scoring_service import ScoringService

    service = ScoringService(db_session)
    template = _seed_ranking_filter_fixture(db_session, service)

    scores = service.get_scores(template_id=template.id)
    assert [s["rank_overall"] for s in scores] == [1, 2, 3, 4]
    assert [s["rank_overall_original"] for s in scores] == [1, 2, 3, 4]
