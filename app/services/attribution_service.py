"""Performance attribution service.

Simplified Brinson model for analyzing return sources.
"""

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.data.repositories import price_repository
from app.models.etl import BacktestResult


class AttributionService:
    """Service for performance attribution analysis."""

    def __init__(self, db: Session):
        self.db = db

    def _calculate_benchmark_return(
        self,
        etf_code: str,
        start_date: date,
        end_date: date,
    ) -> float:
        """Calculate buy-and-hold benchmark return using adjusted close prices."""
        df = price_repository.get_bars(
            self.db, etf_code, start_date, end_date, adjusted=True
        )
        if df.empty or len(df) < 2:
            return 0.0

        first_close = float(df["adj_close"].iloc[0])
        last_close = float(df["adj_close"].iloc[-1])
        if first_close > 0:
            return (last_close - first_close) / first_close * 100
        return 0.0

    def _parse_date(self, value: Any) -> date | None:
        """Parse a date value from string or date object."""
        if value is None:
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return date.fromisoformat(value)
        return None

    def analyze_backtest(self, backtest_id: int) -> dict[str, Any]:
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

        total_return = metrics.get("total_return", 0)
        etf_code = config.get("etf_code") or ""
        start_date = self._parse_date(backtest.start_date)
        end_date = self._parse_date(backtest.end_date)

        # Calculate benchmark return (buy and hold)
        benchmark_return = 0.0
        if etf_code and start_date and end_date:
            benchmark_return = self._calculate_benchmark_return(
                etf_code, start_date, end_date
            )

        excess_return = total_return - benchmark_return
        total_days = metrics.get("trading_days", 252)

        # Calculate actual days in market across all closed trades
        in_market_days = 0
        if trades:
            for t in trades:
                entry = self._parse_date(t.get("entry_date"))
                exit_ = self._parse_date(t.get("exit_date"))
                if entry and exit_ and exit_ >= entry:
                    in_market_days += (exit_ - entry).days + 1

            allocation_ratio = in_market_days / total_days if total_days > 0 else 1.0
            avg_trade_return = sum(t.get("pnl_pct", 0) for t in trades) / len(trades) if trades else 0

            allocation_effect = benchmark_return * (allocation_ratio - 1.0)
            selection_effect = avg_trade_return * allocation_ratio
            interaction_effect = total_return - allocation_effect - selection_effect
        else:
            allocation_ratio = 0.0
            allocation_effect = 0
            selection_effect = 0
            interaction_effect = 0
            avg_trade_return = 0

        denominator = total_return if total_return != 0 else 1

        return {
            "backtest_id": backtest_id,
            "total_return": round(total_return, 2),
            "benchmark_return": round(benchmark_return, 2),
            "excess_return": round(excess_return, 2),
            "attribution": {
                "allocation_effect": round(allocation_effect, 2),
                "selection_effect": round(selection_effect, 2),
                "interaction_effect": round(interaction_effect, 2),
            },
            "summary": {
                "allocation_pct": round(allocation_effect / denominator * 100, 2),
                "selection_pct": round(selection_effect / denominator * 100, 2),
                "interaction_pct": round(interaction_effect / denominator * 100, 2),
                "in_market_pct": round(allocation_ratio * 100, 2),
                "avg_trade_return": round(avg_trade_return, 2),
            },
            "trade_stats": {
                "total_trades": len(trades),
                "winning_trades": sum(1 for t in trades if t.get("pnl_pct", 0) > 0),
                "losing_trades": sum(1 for t in trades if t.get("pnl_pct", 0) <= 0),
            },
        }
