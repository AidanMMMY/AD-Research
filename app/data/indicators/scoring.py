"""ETF scoring calculation engine.

Provides percentile-based scoring for ETFs across multiple dimensions
with configurable weight templates.
"""

from typing import Any

import numpy as np
from scipy.stats import rankdata


class ScoreCalculator:
    """Calculate composite scores for ETFs using percentile ranking.

    For each dimension, computes percentile ranks of the metric values,
    adjusts direction (asc/desc), and weights into a composite score.
    """

    def calculate_scores(
        self,
        indicators: list[dict[str, Any]],
        template_weights: dict[str, dict[str, Any]],
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
            dim_values = []
            valid_codes = []

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

            # Percentile ranking (0 to 100).
            # rankdata assigns ranks starting at 1; transform to 0-based percentiles
            # so the worst performer gets 0 and the best gets 100.
            ranks = rankdata(dim_values, method="average")
            n = len(dim_values)
            if n > 1:
                percentiles = ((ranks - 1) / (n - 1)) * 100
            else:
                percentiles = np.full_like(ranks, 50.0, dtype=float)

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
