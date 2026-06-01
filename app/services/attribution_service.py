"""Performance attribution service.

Simplified Brinson model for analyzing return sources.
"""

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.etl import BacktestResult


class AttributionService:
    """Service for performance attribution analysis."""

    def __init__(self, db: Session):
        self.db = db

    def analyze_backtest(self, backtest_id: int) -> Dict[str, Any]:
        """Analyze a backtest's return attribution.

        Uses a simplified Brinson model:
        - Allocation Effect (timing): from strategy's ability to be in market
        - Selection Effect (picking): from choosing right entry/exit points
        - Interaction Effect: residual

        Args:
            backtest_id: Backtest result ID.

        Returns:
            Dict with attribution breakdown.
        """
        backtest = (
            self.db.query(BacktestResult)
            .filter(BacktestResult.id == backtest_id)
            .first()
        )
        if not backtest:
            return {"error": "Backtest not found"}

        metrics = backtest.metrics or {}
        trades = backtest.trades or []
        config = backtest.config_snapshot or {}

        # Calculate benchmark return (buy and hold)
        benchmark_return = metrics.get("total_return", 0)

        # If there are trades, calculate attribution
        if trades:
            # Allocation effect: proportion of time in market vs out
            in_market_days = sum(
                1 for t in trades if t.get("exit_date")
            )
            total_days = metrics.get("trading_days", 252)
            allocation_ratio = in_market_days / total_days if total_days > 0 else 1.0

            # Selection effect: average trade return vs benchmark
            avg_trade_return = sum(t.get("pnl_pct", 0) for t in trades) / len(trades) if trades else 0

            allocation_effect = benchmark_return * (allocation_ratio - 1.0)
            selection_effect = avg_trade_return * allocation_ratio
            interaction_effect = metrics.get("total_return", 0) - allocation_effect - selection_effect
        else:
            allocation_effect = 0
            selection_effect = 0
            interaction_effect = 0

        return {
            "backtest_id": backtest_id,
            "total_return": round(metrics.get("total_return", 0), 2),
            "benchmark_return": round(benchmark_return, 2),
            "excess_return": round(metrics.get("total_return", 0) - benchmark_return, 2),
            "attribution": {
                "allocation_effect": round(allocation_effect, 2),
                "selection_effect": round(selection_effect, 2),
                "interaction_effect": round(interaction_effect, 2),
            },
            "summary": {
                "allocation_pct": round(allocation_effect / metrics.get("total_return", 1) * 100, 2) if metrics.get("total_return", 0) != 0 else 0,
                "selection_pct": round(selection_effect / metrics.get("total_return", 1) * 100, 2) if metrics.get("total_return", 0) != 0 else 0,
                "interaction_pct": round(interaction_effect / metrics.get("total_return", 1) * 100, 2) if metrics.get("total_return", 0) != 0 else 0,
            },
            "trade_stats": {
                "total_trades": len(trades),
                "winning_trades": sum(1 for t in trades if t.get("pnl_pct", 0) > 0),
                "losing_trades": sum(1 for t in trades if t.get("pnl_pct", 0) <= 0),
            },
        }
