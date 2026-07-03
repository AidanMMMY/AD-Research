from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PoolMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    etf_code: str
    etf_name: str | None = None
    name_zh: str | None = None
    added_at: datetime | None = None
    notes: str | None = None


class PoolBase(BaseModel):
    name: str
    description: str | None = None


class PoolCreate(PoolBase):
    # M21-3: owner-scoped pool. Optional for backward compatibility; the API
    # layer will default it to the caller's id when not provided.
    user_id: int | None = None


class PoolUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class PoolResponse(PoolBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int | None = None
    members: list[PoolMemberResponse] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PoolMemberCreate(BaseModel):
    etf_code: str
    notes: str | None = None


# ------------------------------------------------------------------
# Pool enhancement schemas
# ------------------------------------------------------------------

class PoolWeightResponse(BaseModel):
    """Response model for pool weight configuration."""

    model_config = ConfigDict(from_attributes=True)
    etf_code: str
    etf_name: str | None = None
    name_zh: str | None = None
    target_weight: float = 0.0
    suggested_weight: float | None = None
    weight_source: str = "manual"
    updated_at: datetime | None = None


class PoolWeightUpdateRequest(BaseModel):
    """Request model for updating a pool weight."""

    target_weight: float = Field(..., ge=0, le=100)


class PoolWeightSuggestRequest(BaseModel):
    """Request model for weight suggestion."""

    algorithm: str = "equal"
    template_id: int | None = None


class PoolWeightSuggestResponse(BaseModel):
    """Response model for a single weight suggestion."""

    etf_code: str
    etf_name: str | None = None
    name_zh: str | None = None
    suggested_weight: float
    algorithm: str


class PoolAnalyticsMember(BaseModel):
    """Member info within pool analytics."""

    etf_code: str
    etf_name: str | None = None
    name_zh: str | None = None
    category: str | None = None
    target_weight: float = 0.0
    added_at: datetime | None = None


class PoolAnalyticsResponse(BaseModel):
    """Comprehensive pool analytics response."""

    pool_id: int
    pool_name: str | None = None
    member_count: int = 0
    members: list[PoolAnalyticsMember] = []
    category_distribution: dict[str, Any] = {}
    performance: dict[str, float] = {}
    rebalance_needed: bool = False
    rebalance_alerts: list[dict[str, Any]] = []


class PoolSnapshotResponse(BaseModel):
    """Response model for pool snapshot."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    pool_id: int
    snapshot_date: date
    created_at: datetime | None = None
    data: dict[str, Any] = {}


class PoolCorrelationResponse(BaseModel):
    """Response model for pool correlation matrix."""

    codes: list[str]
    matrix: list[list[float]]
