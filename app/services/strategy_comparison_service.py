"""Strategy comparison service.

Compares performance across multiple backtests.
"""

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.etl import BacktestResult


class StrategyComparisonService:
    """Service for comparing strategies."""

    def __init__(self, db: Session):
        self.db = db

    def compare_backtests(self, backtest_ids: List[int]) -> Dict[str, Any]:
        """Compare multiple backtest results.

        Args:
            backtest_ids: List of backtest result IDs.

        Returns:
            Dict with comparison data.
        """
        backtests = (
            self.db.query(BacktestResult)
            .filter(BacktestResult.id.in_(backtest_ids))
            .all()
        )

        if not backtests:
            return {"items": [], "correlation_matrix": []}

        items = []
        for b in backtests:
            metrics = b.metrics or {}
            config = b.config_snapshot or {}
            items.append({
                "backtest_id": b.id,
                "strategy_id": b.strategy_id,
                "etf_code": config.get("etf_code", "Unknown"),
                "strategy_type": config.get("strategy_type", "Unknown"),
                "start_date": b.start_date.isoformat() if b.start_date else None,
                "end_date": b.end_date.isoformat() if b.end_date else None,
                "metrics": {
                    "total_return": metrics.get("total_return", 0),
                    "annualized_return": metrics.get("annualized_return", 0),
                    "max_drawdown": metrics.get("max_drawdown", 0),
                    "sharpe_ratio": metrics.get("sharpe_ratio", 0),
                    "win_rate": metrics.get("win_rate", 0),
                    "trade_count": metrics.get("trade_count", 0),
                },
            })

        return {
            "items": items,
            "count": len(items),
        }
