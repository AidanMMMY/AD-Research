"""Attribution Pydantic schemas."""

from typing import Any, Dict

from pydantic import BaseModel


class AttributionBreakdown(BaseModel):
    """Attribution breakdown."""

    allocation_effect: float
    selection_effect: float
    interaction_effect: float


class AttributionPercentages(BaseModel):
    """Attribution percentages."""

    allocation_pct: float
    selection_pct: float
    interaction_pct: float


class TradeStats(BaseModel):
    """Trade statistics."""

    total_trades: int
    winning_trades: int
    losing_trades: int


class AttributionResponse(BaseModel):
    """Attribution analysis response."""

    backtest_id: int
    total_return: float
    benchmark_return: float
    excess_return: float
    attribution: AttributionBreakdown
    summary: AttributionPercentages
    trade_stats: TradeStats
