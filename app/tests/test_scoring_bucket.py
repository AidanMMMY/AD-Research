"""Tests for bucket-aware percentile ranking in the scoring engine.

Verifies that:
- Within-category ranking isolates instruments from different classes
  (e.g. a 4% vol bond ETF is not crushed by a 30% QDII ETF in the
  "risk" dimension).
- Unknown categories fall into a ``__unknown__`` bucket and still
  receive a rank.
- NaN metric values propagate correctly through the bucket logic.
- Legacy global ranking is preserved as the opt-out path.
"""

import numpy as np
import pandas as pd
import pytest

from app.data.indicators.scoring import (
    BUCKET_AWARE_DIMENSIONS,
    ScoreCalculator,
    bucket_aware_rank,
)


# ---------------------------------------------------------------------------
# Helper-level tests
# ---------------------------------------------------------------------------


def test_bucket_aware_rank_isolates_categories():
    """A high absolute value in one bucket must not push another bucket's
    best performer to a low percentile."""
    codes = pd.Series(["A", "B", "C", "D", "E", "F"])
    dim_values = pd.Series(
        [0.10, 0.20, 0.30, 0.04, 0.05, 0.06]  # Equity cluster + Bond cluster
    )
    category_map = {
        "A": "Equity",
        "B": "Equity",
        "C": "Equity",
        "D": "Bond",
        "E": "Bond",
        "F": "Bond",
    }

    out = bucket_aware_rank(dim_values, codes, category_map)
    out_by_code = dict(zip(codes.tolist(), out.tolist(), strict=False))

    # Within Equity: C (highest) should be 1.0, A (lowest) should be 0.0.
    assert out_by_code["C"] == pytest.approx(1.0)
    assert out_by_code["A"] == pytest.approx(0.0)

    # Within Bond: F (highest) should be 1.0, D (lowest) should be 0.0.
    assert out_by_code["F"] == pytest.approx(1.0)
    assert out_by_code["D"] == pytest.approx(0.0)


def test_bucket_aware_rank_unknown_category_fallback():
    """Codes without a category map into the __unknown__ bucket."""
    codes = pd.Series(["X", "Y", "Z", "W"])
    dim_values = pd.Series([0.1, 0.2, 0.3, 0.4])
    category_map = {
        "X": "Equity",
        "Y": "Equity",
        # Z and W have no category — they should still get ranked.
    }

    out = bucket_aware_rank(dim_values, codes, category_map)
    out_by_code = dict(zip(codes.tolist(), out.tolist(), strict=False))

    # Equity bucket contains X, Y → X (lowest) should be 0.0 and
    # Y (highest) should be 1.0. (No ties here, so scipy's "average"
    # rankdata returns the standard 0/1 endpoints.)
    assert out_by_code["X"] == pytest.approx(0.0)
    assert out_by_code["Y"] == pytest.approx(1.0)

    # Unknown bucket contains Z, W → Z should be 0.0, W should be 1.0.
    assert out_by_code["Z"] == pytest.approx(0.0)
    assert out_by_code["W"] == pytest.approx(1.0)


def test_bucket_aware_rank_nan_propagation():
    """NaN values within a bucket should remain NaN; the bucket still
    ranks the non-NaN values against each other."""
    codes = pd.Series(["A", "B", "C", "D"])
    dim_values = pd.Series([0.10, np.nan, 0.30, 0.05])
    category_map = {"A": "Equity", "B": "Equity", "C": "Equity", "D": "Equity"}

    out = bucket_aware_rank(dim_values, codes, category_map)
    out_by_code = dict(zip(codes.tolist(), out.tolist(), strict=False))

    assert np.isnan(out_by_code["B"])
    # C has the highest valid value → 1.0. D has the lowest → 0.0.
    assert out_by_code["C"] == pytest.approx(1.0)
    assert out_by_code["D"] == pytest.approx(0.0)
    assert out_by_code["A"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# ScoreCalculator-level tests
# ---------------------------------------------------------------------------


def test_calculator_uses_bucket_ranking_by_default():
    """When category_map is provided and bucket-aware is on, a strong
    cross-bucket performer must not dominate the score."""
    indicators = [
        # Equity bucket — big absolute returns.
        {"etf_code": "EQ_LO", "return_1y": 0.20},
        {"etf_code": "EQ_MID", "return_1y": 0.30},
        {"etf_code": "EQ_HI", "return_1y": 0.40},
        # Bond bucket — modest absolute returns. BOND_HI should still
        # win the bond bucket, not get crushed by EQ_HI in the global
        # ranking.
        {"etf_code": "BOND_LO", "return_1y": 0.03},
        {"etf_code": "BOND_HI", "return_1y": 0.07},
    ]
    category_map = {
        "EQ_LO": "Equity",
        "EQ_MID": "Equity",
        "EQ_HI": "Equity",
        "BOND_LO": "Bond",
        "BOND_HI": "Bond",
    }
    template_weights = {
        "return": {"metrics": ["return_1y"], "weight": 1.0, "direction": "asc"},
    }

    calc = ScoreCalculator()
    scores_bucketed = calc.calculate_scores(
        indicators,
        template_weights,
        category_map=category_map,
        enable_bucket_aware=True,
    )

    # Within the bond bucket, BOND_HI should beat BOND_LO.
    assert scores_bucketed["BOND_HI"]["return"] > scores_bucketed["BOND_LO"]["return"]
    # Within the equity bucket, EQ_HI should beat EQ_LO.
    assert scores_bucketed["EQ_HI"]["return"] > scores_bucketed["EQ_LO"]["return"]
    # Both bucket winners should land at the top of their respective
    # buckets (100 = best in bucket).
    assert scores_bucketed["EQ_HI"]["return"] == pytest.approx(100.0)
    assert scores_bucketed["BOND_HI"]["return"] == pytest.approx(100.0)


def test_calculator_legacy_path_still_works():
    """enable_bucket_aware=False must reproduce the old global ranking
    behaviour (rollback path)."""
    indicators = [
        {"etf_code": "EQ_HI", "return_1y": 0.40},
        {"etf_code": "EQ_LO", "return_1y": 0.20},
        {"etf_code": "BOND_HI", "return_1y": 0.07},
    ]
    category_map = {"EQ_HI": "Equity", "EQ_LO": "Equity", "BOND_HI": "Bond"}
    template_weights = {
        "return": {"metrics": ["return_1y"], "weight": 1.0, "direction": "asc"},
    }

    calc = ScoreCalculator()
    scores_legacy = calc.calculate_scores(
        indicators,
        template_weights,
        category_map=category_map,
        enable_bucket_aware=False,
    )

    # In the legacy path, EQ_HI ranks highest, BOND_HI lowest.
    assert scores_legacy["EQ_HI"]["return"] == pytest.approx(100.0)
    assert scores_legacy["BOND_HI"]["return"] == pytest.approx(0.0)


def test_calculator_risk_dimension_uses_bucket_zscore():
    """For the risk dimension, the bucket z-score path should make a
    bond ETF with *higher* absolute vol still score worse than a
    bond ETF with lower vol — but without being globally crushed by
    QDIIs."""
    indicators = [
        # QDII bucket: high absolute vol.
        {"etf_code": "QDII_A", "volatility_20d": 0.25},
        {"etf_code": "QDII_B", "volatility_20d": 0.35},
        # Bond bucket: low absolute vol.
        {"etf_code": "BOND_A", "volatility_20d": 0.03},
        {"etf_code": "BOND_B", "volatility_20d": 0.05},
    ]
    category_map = {
        "QDII_A": "QDII",
        "QDII_B": "QDII",
        "BOND_A": "Bond",
        "BOND_B": "Bond",
    }
    template_weights = {
        "risk": {"metrics": ["volatility_20d"], "weight": 1.0, "direction": "desc"},
    }

    calc = ScoreCalculator()
    scores = calc.calculate_scores(
        indicators,
        template_weights,
        category_map=category_map,
        enable_bucket_aware=True,
        use_bucket_zscore_for_risk=True,
    )

    # Lower vol within each bucket should score higher (desc direction).
    assert scores["QDII_A"]["risk"] > scores["QDII_B"]["risk"]
    assert scores["BOND_A"]["risk"] > scores["BOND_B"]["risk"]
    # With z-score, the relative position inside each bucket is what
    # matters — both bucket winners should land near the top.
    assert scores["QDII_A"]["risk"] == pytest.approx(100.0)
    assert scores["BOND_A"]["risk"] == pytest.approx(100.0)


def test_calculator_risk_uses_absolute_vol_when_zscore_off():
    """Disabling z-score should fall back to bucket rank on the raw
    absolute volatility — which is closer to the old behavior, just
    bucketed."""
    indicators = [
        {"etf_code": "QDII_A", "volatility_20d": 0.25},
        {"etf_code": "QDII_B", "volatility_20d": 0.35},
        {"etf_code": "BOND_A", "volatility_20d": 0.03},
        {"etf_code": "BOND_B", "volatility_20d": 0.05},
    ]
    category_map = {
        "QDII_A": "QDII",
        "QDII_B": "QDII",
        "BOND_A": "Bond",
        "BOND_B": "Bond",
    }
    template_weights = {
        "risk": {"metrics": ["volatility_20d"], "weight": 1.0, "direction": "desc"},
    }

    calc = ScoreCalculator()
    scores = calc.calculate_scores(
        indicators,
        template_weights,
        category_map=category_map,
        enable_bucket_aware=True,
        use_bucket_zscore_for_risk=False,
    )

    # Within each bucket, desc direction means lower vol wins.
    assert scores["QDII_A"]["risk"] > scores["QDII_B"]["risk"]
    assert scores["BOND_A"]["risk"] > scores["BOND_B"]["risk"]
    # Bucket winners should still land at the top of their bucket.
    assert scores["QDII_A"]["risk"] == pytest.approx(100.0)
    assert scores["BOND_A"]["risk"] == pytest.approx(100.0)


def test_bucket_aware_dimensions_constant():
    """Sanity check on the bucket-aware dimension set — currently the
    'return' and 'risk' dimensions are bucketed. If the intent changes,
    update this assertion in tandem with the production constant."""
    assert "return" in BUCKET_AWARE_DIMENSIONS
    assert "risk" in BUCKET_AWARE_DIMENSIONS
