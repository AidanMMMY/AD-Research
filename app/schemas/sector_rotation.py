"""Sector rotation Pydantic schemas.

The contract is intentionally **backward-compatible at the response-shape
level** — endpoint URLs, query params and top-level keys stay the same —
but the semantics of ``sector`` (was: ETF 基金类型 like "股票型"; now:
GICS industry sector like "Information Technology") have changed.

See ``app/services/sector_rotation_service.py`` for the rationale.
"""


from typing import Literal

from pydantic import BaseModel, Field


class SectorScope(BaseModel):
    """Universe scope of the analysis."""

    market: Literal["A股"] = Field(..., description="Trading market scope")
    instrument_types: list[Literal["ETF", "STOCK"]] = Field(
        ..., description="Instrument types included"
    )
    classification: Literal["GICS"] = Field(
        ..., description="Industry classification system"
    )


class SectorPerformance(BaseModel):
    """Sector performance metrics (per GICS sector)."""

    sector: str = Field(..., description="GICS sector name (level-1)")
    count: int = Field(..., description="Total instruments in the sector")
    stock_count: int = Field(..., description="Individual stock count")
    etf_count: int = Field(..., description="ETF count")
    return_1w: float = Field(..., description="1-week average return (%)")
    return_1m: float = Field(..., description="1-month average return (%)")
    return_3m: float = Field(..., description="3-month average return (%)")
    return_6m: float = Field(..., description="6-month average return (%)")
    return_1y: float = Field(..., description="1-year average return (%)")
    sharpe_1y: float = Field(..., description="1-year Sharpe (average)")
    volatility_20d: float = Field(..., description="20-day volatility (average)")
    rsi14: float = Field(..., description="RSI14 (average)")
    amount_total: float = Field(..., description="Aggregate turnover (元)")
    relative_strength_1w: float = Field(
        ..., description="Relative strength vs market avg (1w)"
    )
    relative_strength_1m: float = Field(
        ..., description="Relative strength vs market avg (1m)"
    )
    relative_strength_3m: float = Field(
        ..., description="Relative strength vs market avg (3m)"
    )
    momentum_rank: int = Field(..., description="Rank by 1m return (1=best)")


class RotationSignal(BaseModel):
    """Sector rotation signal — sector moved up/down ≥3 positions in rank."""

    sector: str
    type: str  # "up" or "down"
    message: str
    current_rank: int
    previous_rank: int
    rank_change: int = Field(
        ..., description="Positive = moved up; negative = moved down"
    )


class MarketAverage(BaseModel):
    """Market-average metrics across all sectors in scope."""

    return_1w: float
    return_1m: float
    return_3m: float
    return_6m: float
    return_1y: float
    sharpe_1y: float


class SectorRotationResponse(BaseModel):
    """Sector rotation analysis response."""

    trade_date: str
    scope: SectorScope
    sectors: list[SectorPerformance]
    market_avg: MarketAverage | None
    rotation_signals: list[RotationSignal]


class SectorListItem(BaseModel):
    """Sector list item — distinct sector with composition counts."""

    sector: str
    count: int
    stock_count: int
    etf_count: int


class SectorListResponse(BaseModel):
    """Sector list response."""

    items: list[SectorListItem]