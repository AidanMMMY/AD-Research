"""Scoring system Pydantic schemas.

Provides request/response models for score templates and ETF composite scores.
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

# ------------------------------------------------------------------
# ScoreTemplate schemas
# ------------------------------------------------------------------

class ScoreTemplateBase(BaseModel):
    """Base schema for score template fields."""

    name: str
    description: str | None = None
    weights: dict[str, Any]
    is_default: bool = False


class ScoreTemplateCreate(ScoreTemplateBase):
    """Schema for creating a new score template."""

    pass


class ScoreTemplateUpdate(BaseModel):
    """Schema for updating an existing score template."""

    name: str | None = None
    description: str | None = None
    weights: dict[str, Any] | None = None
    is_default: bool | None = None


class ScoreTemplateResponse(ScoreTemplateBase):
    """Schema for score template responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ------------------------------------------------------------------
# ETFScore schemas
# ------------------------------------------------------------------

class ETFScoreResponse(BaseModel):
    """Schema for ETF composite score responses.

    Includes all score fields along with ETF metadata (name, market, category)
    and the trade date for the score snapshot.
    """

    etf_code: str
    etf_name: str | None = None
    market: str | None = None
    category: str | None = None
    trade_date: date | None = None
    composite_score: float | None = None
    score_return: float | None = None
    score_risk: float | None = None
    score_sharpe: float | None = None
    score_liquidity: float | None = None
    score_trend: float | None = None
    rank_overall: int | None = None
    rank_category: int | None = None
    return_1m: float | None = None
    return_3m: float | None = None
    return_1y: float | None = None


class ETFScoreListResponse(BaseModel):
    """Schema for a paginated list of ETF scores."""

    items: list[ETFScoreResponse]
    total: int
    template_id: int
    trade_date: date | None = None
