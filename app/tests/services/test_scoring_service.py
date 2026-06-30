"""Tests for ScoringService.

Covers template CRUD, dimension map constants, and empty-state behaviour
of the daily-score calculation entry point.
"""

from app.services.scoring_service import ScoringService


def test_service_initializes_with_calculator(db_session):
    svc = ScoringService(db_session)
    assert svc.calculator is not None
    assert "return" in svc.DIMENSION_MAP
    assert "risk" in svc.DIMENSION_MAP
    assert "sharpe" in svc.DIMENSION_MAP
    assert "liquidity" in svc.DIMENSION_MAP
    assert "trend" in svc.DIMENSION_MAP


def test_dimension_map_has_required_fields(db_session):
    svc = ScoringService(db_session)
    for dim, conf in svc.DIMENSION_MAP.items():
        assert "metrics" in conf and len(conf["metrics"]) > 0
        assert "weight" in conf
        assert conf["weight"] > 0
        assert "direction" in conf
        assert conf["direction"] in ("asc", "desc")


def test_template_crud_roundtrip(db_session):
    svc = ScoringService(db_session)
    t = svc.create_template(
        name="My-Template",
        description="test",
        weights={"return": 0.5, "risk": 0.5},
        is_default=False,
    )
    assert t.id is not None
    assert svc.get_template(t.id).name == "My-Template"
    assert any(x.name == "My-Template" for x in svc.get_templates())


def test_get_default_template_returns_default(db_session):
    svc = ScoringService(db_session)
    svc.create_template(
        name="Defaulted",
        description="",
        weights={"return": 1.0},
        is_default=True,
    )
    default = svc.get_default_template()
    assert default is not None
    assert default.is_default is True


def test_init_default_templates_seeds_three(db_session):
    svc = ScoringService(db_session)
    svc._init_default_templates()
    names = {t.name for t in svc.get_templates()}
    assert {"保守型", "均衡型", "进取型"} <= names


def test_build_template_weights_merges_dimensions(db_session):
    svc = ScoringService(db_session)
    t = svc.create_template(
        name="Custom",
        description="",
        weights={"return": 0.7, "risk": 0.3},
    )
    result = svc._build_template_weights(t)
    assert result["return"]["weight"] == 0.7
    assert result["risk"]["weight"] == 0.3
    # Unspecified dimensions still present with default weight
    assert "liquidity" in result
    assert "trend" in result


def test_calculate_daily_scores_returns_empty_when_no_data(db_session):
    svc = ScoringService(db_session)
    # No indicators in DB -> empty result
    result = svc.calculate_daily_scores()
    assert result == {}


def test_safe_float_helper_handles_invalid():
    from app.services.scoring_service import _safe_float

    assert _safe_float(None) is None
    assert _safe_float("not a number") is None
    assert _safe_float(float("nan")) is None
    assert _safe_float(float("inf")) is None
    assert _safe_float(0) == 0.0
    assert _safe_float("3.14") == 3.14
