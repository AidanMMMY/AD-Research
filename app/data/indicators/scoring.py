"""ETF scoring calculation engine.

Provides percentile-based scoring for ETFs across multiple dimensions
with configurable weight templates.

Supports bucket-aware ranking (per-category percentile ranking) to avoid
mixing instrument types that have very different risk/return profiles
(e.g.国债 ETF vs QDII). Set ``enable_bucket_aware=True`` (default) to
rank within category buckets; fall back to the legacy global ranking
with ``enable_bucket_aware=False``.
"""

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import rankdata

# Dimensions whose absolute values differ wildly across asset classes
# (e.g. QDII 30% vol vs bond 4% vol). For these we *must* rank inside
# category buckets to avoid low-risk instruments dominating risk scores.
BUCKET_AWARE_DIMENSIONS: set[str] = {"return", "risk"}


def _legacy_rank(dim_values: list[float]) -> np.ndarray:
    """Original global percentile ranking (0-100).

    Ranks all instruments together regardless of category. Retained as
    a fallback / rollback path.
    """
    arr = np.asarray(dim_values, dtype=float)
    ranks = rankdata(arr, method="average")
    n = len(arr)
    if n > 1:
        percentiles = ((ranks - 1) / (n - 1)) * 100
    else:
        percentiles = np.full_like(ranks, 50.0, dtype=float)
    return percentiles


def bucket_aware_rank(
    dim_values: pd.Series,
    codes: pd.Series,
    category_map: dict[str, str] | None,
) -> pd.Series:
    """Percentile rank (0-1) within category buckets.

    Args:
        dim_values: Numeric values to rank. NaN entries are preserved as NaN.
        codes: ETF codes aligned with ``dim_values``. Used to look up
            category from ``category_map``.
        category_map: Dict mapping etf_code → category. Codes missing
            from the map fall into a ``__unknown__`` bucket so they
            still receive a rank rather than being silently dropped.

    Returns:
        A ``pd.Series`` of percentile ranks (0.0–1.0) aligned to the
        input index. Higher percentile = better raw value (no direction
        adjustment; callers invert for ``direction == "desc"``).
    """
    cat_map = category_map or {}
    categories = pd.Series(
        [cat_map.get(c, "__unknown__") for c in codes],
        index=dim_values.index,
    )

    result = pd.Series(np.nan, index=dim_values.index, dtype=float)

    for bucket, idx in categories.groupby(categories).groups.items():
        bucket_idx = list(idx)
        bucket_vals = dim_values.loc[bucket_idx]

        # Drop NaN values for the rank computation but remember their
        # positions so we can leave them as NaN in the output.
        valid_mask = ~bucket_vals.isna()
        valid_vals = bucket_vals[valid_mask].to_numpy(dtype=float)
        if len(valid_vals) == 0:
            continue

        ranks = rankdata(valid_vals, method="average")
        n = len(valid_vals)
        if n > 1:
            pct = (ranks - 1) / (n - 1)
        else:
            pct = np.full_like(ranks, 0.5, dtype=float)

        # Place ranked values back at their original positions.
        bucket_result = pd.Series(np.nan, index=bucket_vals.index, dtype=float)
        bucket_result.loc[valid_mask] = pct
        result.loc[bucket_idx] = bucket_result.values

    return result


def _bucket_zscored_rank(
    dim_values: pd.Series,
    codes: pd.Series,
    category_map: dict[str, str] | None,
) -> pd.Series:
    """Z-score within bucket then percentile-rank the z-scores.

    Useful for risk dimensions where absolute values vary by category
    (a 4% bond vol is not "better" than 30% QDII vol per se — the
    bond is just in a different regime). We standardise within the
    bucket so the relative position *within the same instrument class*
    is what gets rewarded, not the absolute level.
    """
    cat_map = category_map or {}
    categories = pd.Series(
        [cat_map.get(c, "__unknown__") for c in codes],
        index=dim_values.index,
    )

    result = pd.Series(np.nan, index=dim_values.index, dtype=float)

    for bucket, idx in categories.groupby(categories).groups.items():
        bucket_idx = list(idx)
        bucket_vals = dim_values.loc[bucket_idx]

        valid_mask = ~bucket_vals.isna()
        valid_vals = bucket_vals[valid_mask].to_numpy(dtype=float)
        if len(valid_vals) == 0:
            continue

        std = valid_vals.std(ddof=0)
        if std == 0 or np.isnan(std):
            # No dispersion → everyone gets the median rank.
            z = np.zeros_like(valid_vals)
        else:
            mean = valid_vals.mean()
            z = (valid_vals - mean) / std

        ranks = rankdata(z, method="average")
        n = len(ranks)
        if n > 1:
            pct = (ranks - 1) / (n - 1)
        else:
            pct = np.full_like(ranks, 0.5, dtype=float)

        bucket_result = pd.Series(np.nan, index=bucket_vals.index, dtype=float)
        bucket_result.loc[valid_mask] = pct
        result.loc[bucket_idx] = bucket_result.values

    return result


class ScoreCalculator:
    """Calculate composite scores for ETFs using percentile ranking.

    For each dimension, computes percentile ranks of the metric values,
    adjusts direction (asc/desc), and weights into a composite score.
    """

    def calculate_scores(
        self,
        indicators: list[dict[str, Any]],
        template_weights: dict[str, dict[str, Any]],
        category_map: dict[str, str] | None = None,
        enable_bucket_aware: bool = True,
        use_bucket_zscore_for_risk: bool = True,
    ) -> dict[str, dict[str, float]]:
        """Calculate composite scores for all ETFs.

        Args:
            indicators: List of dicts with ETF indicator data.
                Each dict must have 'etf_code' and metric fields.
            template_weights: Dict mapping dimension name to config:
                {
                    "return": {
                        "metrics": ["return_1y", "return_3m"],
                        "weight": 0.3,
                        "direction": "asc"  # higher is better
                    },
                    "risk": {
                        "metrics": ["volatility_20d"],
                        "weight": 0.2,
                        "direction": "desc"  # lower is better
                    }
                }
            category_map: Optional dict mapping etf_code → category.
                When provided (and ``enable_bucket_aware`` is True),
                percentile ranking is performed *within each category
                bucket* rather than across the full universe. Codes
                not in the map fall into a ``__unknown__`` bucket.
            enable_bucket_aware: When True (default) and a category_map
                is supplied, rank inside buckets for dimensions listed
                in ``BUCKET_AWARE_DIMENSIONS``. When False, falls back
                to the legacy global ranking.
            use_bucket_zscore_for_risk: When True (default) and bucket-
                aware ranking is active, the ``risk`` dimension is
                z-scored within each bucket before ranking. This
                prevents low-volatility asset classes (e.g. bond ETFs)
                from dominating the risk score purely because of their
                absolute volatility level.

        Returns:
            Dict mapping etf_code to score dict with dimension scores
            and composite score.
        """
        if not indicators:
            return {}

        results = {}

        # Initialize result structure
        for ind in indicators:
            code = ind.get("etf_code")
            if code:
                results[code] = {"composite": 0.0}

        # Calculate scores per dimension
        for dimension, config in template_weights.items():
            metrics = config.get("metrics", [])
            dim_weight = config.get("weight", 0.0)
            direction = config.get("direction", "asc")

            if not metrics or dim_weight <= 0:
                continue

            # Aggregate multiple metrics in same dimension by averaging
            dim_values: list[float] = []
            valid_codes: list[str] = []

            for ind in indicators:
                code = ind.get("etf_code")
                if not code:
                    continue

                metric_values = []
                for metric in metrics:
                    val = ind.get(metric)
                    if val is not None and not (
                        isinstance(val, float) and np.isnan(val)
                    ):
                        metric_values.append(float(val))

                if metric_values:
                    avg_value = sum(metric_values) / len(metric_values)
                    dim_values.append(avg_value)
                    valid_codes.append(code)

            if not dim_values:
                continue

            # Decide between bucket-aware and legacy ranking.
            use_bucket = (
                enable_bucket_aware
                and category_map is not None
                and dimension in BUCKET_AWARE_DIMENSIONS
            )

            if use_bucket:
                # Use the dimension's first metric as the index label
                # for the series; we only need the values + codes for
                # ranking, so a simple RangeIndex is fine.
                vals_series = pd.Series(dim_values, dtype=float)
                codes_series = pd.Series(valid_codes)
                use_zscore = (
                    use_bucket_zscore_for_risk and dimension == "risk"
                )
                if use_zscore:
                    pct01 = _bucket_zscored_rank(
                        vals_series, codes_series, category_map
                    )
                else:
                    pct01 = bucket_aware_rank(
                        vals_series, codes_series, category_map
                    )
                # bucket_aware_rank returns 0-1; convert to 0-100 to
                # match the legacy scale.
                percentiles = pct01.to_numpy() * 100.0
                # NaNs in bucket_aware_rank propagate to NaNs here.
                # Treat them as 50 (median) so the composite isn't
                # biased to 0 by missing bucket info.
                percentiles = np.where(
                    np.isnan(percentiles), 50.0, percentiles
                )
            else:
                # Legacy global ranking path (rollback / opt-out).
                percentiles = _legacy_rank(dim_values)

            # Adjust direction
            if direction == "desc":
                percentiles = 100 - percentiles

            # Assign dimension scores (raw 0-100 percentile) and accumulate composite
            for code, pct in zip(valid_codes, percentiles, strict=False):
                dim_score = float(pct)
                results[code][dimension] = round(dim_score, 2)
                results[code]["composite"] += dim_score * dim_weight

        # Round composite scores
        for code in results:
            results[code]["composite"] = round(results[code]["composite"], 2)

        return results

    def rank_scores(
        self,
        scores: dict[str, dict[str, float]],
    ) -> dict[str, int]:
        """Compute overall rankings from composite scores.

        Returns dict mapping etf_code to 1-based rank (1 = highest score).
        """
        if not scores:
            return {}

        sorted_items = sorted(
            scores.items(),
            key=lambda x: x[1].get("composite", 0),
            reverse=True,
        )
        return {code: rank + 1 for rank, (code, _) in enumerate(sorted_items)}
