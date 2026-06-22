"""ETF screening Pydantic schemas.

Provides request/response models for ETF screening, ranking, and preset queries.
"""

from typing import Any

from pydantic import BaseModel, Field

# ------------------------------------------------------------------
# Screening filter / result schemas
# ------------------------------------------------------------------

class ScreenFilter(BaseModel):
    """Schema for ETF screening filter parameters.

    All fields are optional. When provided, they define the filtering
    criteria applied to the latest indicator data per ETF.
    """

    market: str | None = Field(None, description="Filter by market (e.g. SH, SZ)")
    category: str | None = Field(None, description="Filter by ETF category")
    rsi_min: float | None = Field(None, ge=0, le=100, description="Minimum RSI14")
    rsi_max: float | None = Field(None, ge=0, le=100, description="Maximum RSI14")
    sharpe_min: float | None = Field(None, description="Minimum Sharpe ratio (1y)")
    sharpe_max: float | None = Field(None, description="Maximum Sharpe ratio (1y)")
    volatility_min: float | None = Field(None, ge=0, description="Minimum 20d volatility")
    volatility_max: float | None = Field(None, ge=0, description="Maximum 20d volatility")
    return_1m_min: float | None = Field(None, description="Minimum 1-month return")
    return_1m_max: float | None = Field(None, description="Maximum 1-month return")
    return_3m_min: float | None = Field(None, description="Minimum 3-month return")
    return_3m_max: float | None = Field(None, description="Maximum 3-month return")
    return_1y_min: float | None = Field(None, description="Minimum 1-year return")
    return_1y_max: float | None = Field(None, description="Maximum 1-year return")
    score_min: float | None = Field(None, ge=0, le=100, description="Minimum composite score")
    score_max: float | None = Field(None, ge=0, le=100, description="Maximum composite score")
    template_id: int | None = Field(None, description="Score template ID for score filtering")
    sort_by: str = Field("composite_score", description="Field to sort by")
    sort_order: str = Field("desc", description="Sort order: asc or desc")
    offset: int = Field(0, ge=0, description="Pagination offset")
    limit: int = Field(50, ge=1, le=500, description="Pagination limit")


class ScreenResultItem(BaseModel):
    """Schema for a single ETF screening result."""

    code: str
    name: str | None = None
    market: str | None = None
    category: str | None = None
    trade_date: str | None = None
    sharpe_1y: float | None = None
    volatility_20d: float | None = None
    rsi14: float | None = None
    return_1m: float | None = None
    return_3m: float | None = None
    return_1y: float | None = None
    max_drawdown_1y: float | None = None
    composite_score: float | None = None
    score_return: float | None = None
    score_risk: float | None = None
    score_sharpe: float | None = None
    score_liquidity: float | None = None
    score_trend: float | None = None
    rank_overall: int | None = None
    rank_category: int | None = None


class ScreenResult(BaseModel):
    """Schema for ETF screening response."""

    items: list[ScreenResultItem]
    count: int
    offset: int
    limit: int
    preset: dict[str, Any] | None = None


# ------------------------------------------------------------------
# Preset schemas
# ------------------------------------------------------------------

class PresetItem(BaseModel):
    """Schema for a screening preset."""

    key: str
    name: str
    description: str
    filters: dict[str, Any]
    sort_by: str
    sort_order: str


class PresetListResponse(BaseModel):
    """Schema for preset list response."""

    presets: list[PresetItem]


# ------------------------------------------------------------------
# Category schemas
# ------------------------------------------------------------------

class CategoryItem(BaseModel):
    """Schema for a category with ETF count."""

    category: str
    count: int


class CategoryListResponse(BaseModel):
    """Schema for category list response."""

    categories: list[CategoryItem]
