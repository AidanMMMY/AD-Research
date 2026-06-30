"""End-to-end test for ScoringService.

Answers the four canonical questions:
  1. Can it run without throwing?
  2. Is the output shape correct?
  3. Are the values sane (no NaN/inf/all-zero)?
  4. Do they match documented behaviour (percentile ranking, ranks 1..N)?
"""

from __future__ import annotations

import math
from datetime import date

import pytest

from app.services.scoring_service import ScoringService


# ---------------------------------------------------------------------------
# Smoke: full daily-scoring pipeline
# ---------------------------------------------------------------------------


def test_scoring_service_full_pipeline_does_what_documented(
    db_session, seeded_etf_universe, default_template
):
    """Run the full calculate_daily_scores pipeline on a seeded universe."""
    svc = ScoringService(db_session)
    trade_date = seeded_etf_universe["trade_date"]

    # 1. Does it run?
    results = svc.calculate_daily_scores(trade_date=trade_date)

    # 2. Output shape: dict[int, int] — template_id -> count
    assert isinstance(results, dict)
    assert results, "Expected at least one template to have produced scores"
    template_id, count = next(iter(results.items()))
    assert isinstance(template_id, int)
    assert isinstance(count, int)
    assert count == 5, f"Expected 5 ETFs scored, got {count}"

    # 3. Persistence check: ETFScore rows must exist and be sane
    scores = svc.get_scores(template_id=template_id, trade_date=trade_date, limit=10)
    assert len(scores) == 5

    expected_keys = {
        "etf_code", "etf_name", "composite_score",
        "score_return", "score_risk", "score_sharpe",
        "score_liquidity", "score_trend",
        "rank_overall", "rank_category",
    }
    for row in scores:
        for key in expected_keys:
            assert key in row, f"Missing key {key} in score row"

        composite = row["composite_score"]
        # Composite must be a finite float, plausibly bounded (weighted avg of 0-100)
        assert isinstance(composite, float)
        assert not math.isnan(composite)
        assert not math.isinf(composite)
        assert 0.0 <= composite <= 100.0, f"Composite {composite} out of range"

        # Each dimension score is 0-100
        for dim in ("score_return", "score_risk", "score_sharpe",
                    "score_liquidity", "score_trend"):
            v = row[dim]
            assert v is not None
            assert 0.0 <= v <= 100.0, f"{dim}={v} out of range"

        # Rank is a positive int
        assert isinstance(row["rank_overall"], int)
        assert row["rank_overall"] >= 1

    # 4. Sanity: rank_overall is 1..5 with no duplicates
    ranks = sorted(row["rank_overall"] for row in scores)
    assert ranks == [1, 2, 3, 4, 5], f"Expected dense 1..5 ranking, got {ranks}"


# ---------------------------------------------------------------------------
# Pure score-calculator behaviour
# ---------------------------------------------------------------------------


def test_score_calculator_pure_returns_monotonic_ordering():
    """ScoreCalculator alone: better return -> higher score (asc direction)."""
    from app.data.indicators.scoring import ScoreCalculator

    calc = ScoreCalculator()
    indicators = [
        {"etf_code": "A", "return_1y": 50.0},
        {"etf_code": "B", "return_1y": 25.0},
        {"etf_code": "C", "return_1y": 5.0},
    ]
    weights = {
        "return": {
            "metrics": ["return_1y"],
            "weight": 1.0,
            "direction": "asc",
        }
    }
    scores = calc.calculate_scores(indicators, weights)
    assert scores["A"]["composite"] > scores["B"]["composite"] > scores["C"]["composite"]
    # A is the best, gets 100th percentile
    assert scores["A"]["return"] == pytest.approx(100.0)
    # C is the worst, gets 0th percentile
    assert scores["C"]["return"] == pytest.approx(0.0)


def test_score_calculator_desc_direction_inverts_ordering():
    """Lower volatility (desc direction) should score higher."""
    from app.data.indicators.scoring import ScoreCalculator

    calc = ScoreCalculator()
    indicators = [
        {"etf_code": "A", "volatility_20d": 5.0},
        {"etf_code": "B", "volatility_20d": 20.0},
        {"etf_code": "C", "volatility_20d": 40.0},
    ]
    weights = {
        "risk": {
            "metrics": ["volatility_20d"],
            "weight": 1.0,
            "direction": "desc",  # lower vol is better
        }
    }
    scores = calc.calculate_scores(indicators, weights)
    # A has the lowest vol -> highest risk score
    assert scores["A"]["composite"] > scores["B"]["composite"] > scores["C"]["composite"]


def test_score_calculator_rank_scores_1_based():
    """rank_scores returns 1-based rank (1 = highest)."""
    from app.data.indicators.scoring import ScoreCalculator

    calc = ScoreCalculator()
    scores = {"A": {"composite": 90.0}, "B": {"composite": 60.0}, "C": {"composite": 80.0}}
    ranks = calc.rank_scores(scores)
    assert ranks == {"A": 1, "C": 2, "B": 3}


# ---------------------------------------------------------------------------
# Template CRUD
# ---------------------------------------------------------------------------


def test_scoring_service_template_create_and_get(db_session):
    """Template CRUD round-trip persists weights correctly."""
    svc = ScoringService(db_session)
    t = svc.create_template(
        name="E2E Custom",
        description="Custom weights",
        weights={"return": 0.6, "risk": 0.4},
    )
    assert t.id is not None
    fetched = svc.get_template(t.id)
    assert fetched is not None
    assert fetched.weights == {"return": 0.6, "risk": 0.4}
