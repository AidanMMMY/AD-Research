from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class PoolMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    etf_code: str
    etf_name: Optional[str] = None
    added_at: Optional[datetime] = None
    notes: Optional[str] = None


class PoolBase(BaseModel):
    name: str
    description: Optional[str] = None


class PoolCreate(PoolBase):
    pass


class PoolUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class PoolResponse(PoolBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    members: List[PoolMemberResponse] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PoolMemberCreate(BaseModel):
    etf_code: str
    notes: Optional[str] = None


# ------------------------------------------------------------------
# Pool enhancement schemas
# ------------------------------------------------------------------

class PoolWeightResponse(BaseModel):
    """Response model for pool weight configuration."""

    model_config = ConfigDict(from_attributes=True)
    etf_code: str
    etf_name: Optional[str] = None
    target_weight: float = 0.0
    suggested_weight: Optional[float] = None
    weight_source: str = "manual"
    updated_at: Optional[datetime] = None


class PoolWeightUpdateRequest(BaseModel):
    """Request model for updating a pool weight."""

    target_weight: float


class PoolWeightSuggestRequest(BaseModel):
    """Request model for weight suggestion."""

    algorithm: str = "equal"
    template_id: Optional[int] = None


class PoolWeightSuggestResponse(BaseModel):
    """Response model for a single weight suggestion."""

    etf_code: str
    etf_name: Optional[str] = None
    suggested_weight: float
    algorithm: str


class PoolAnalyticsMember(BaseModel):
    """Member info within pool analytics."""

    etf_code: str
    etf_name: Optional[str] = None
    category: Optional[str] = None
    target_weight: float = 0.0
    added_at: Optional[datetime] = None


class PoolAnalyticsResponse(BaseModel):
    """Comprehensive pool analytics response."""

    pool_id: int
    pool_name: Optional[str] = None
    member_count: int = 0
    members: List[PoolAnalyticsMember] = []
    category_distribution: Dict[str, Any] = {}
    performance: Dict[str, float] = {}
    rebalance_needed: bool = False
    rebalance_alerts: List[Dict[str, Any]] = []


class PoolSnapshotResponse(BaseModel):
    """Response model for pool snapshot."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    pool_id: int
    snapshot_date: date
    created_at: Optional[datetime] = None


class PoolCorrelationResponse(BaseModel):
    """Response model for pool correlation matrix."""

    codes: List[str]
    matrix: List[List[float]]
