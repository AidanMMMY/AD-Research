"""Sector rotation Pydantic schemas."""

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class SectorPerformance(BaseModel):
    """Sector performance metrics."""

    category: str
    count: int
    return_1m: float
    return_3m: float
    sharpe_1y: float
    volatility_20d: float
    rsi14: float
    relative_strength_1m: float
    relative_strength_3m: float
    momentum_rank: int


class RotationSignal(BaseModel):
    """Sector rotation signal."""

    category: str
    type: str  # "up" or "down"
    message: str
    current_rank: int
    previous_rank: int


class MarketAverage(BaseModel):
    """Market average metrics."""

    return_1m: float
    return_3m: float
    sharpe_1y: float


class SectorRotationResponse(BaseModel):
    """Sector rotation analysis response."""

    trade_date: str
    sectors: List[SectorPerformance]
    market_avg: MarketAverage
    rotation_signals: List[RotationSignal]


class SectorListItem(BaseModel):
    """Sector list item."""

    category: str
    count: int


class SectorListResponse(BaseModel):
    """Sector list response."""

    items: List[SectorListItem]
