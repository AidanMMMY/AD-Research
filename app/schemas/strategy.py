"""Strategy Pydantic schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class StrategyTemplate(BaseModel):
    """Preset strategy template."""

    name: str
    description: str
    strategy_type: str
    params: Dict[str, Any]


class StrategyBase(BaseModel):
    """Base strategy schema."""

    name: str
    description: Optional[str] = None
    strategy_type: str
    params: Dict[str, Any]
    is_active: bool = True


class StrategyCreate(StrategyBase):
    """Create strategy schema."""

    pass


class StrategyUpdate(BaseModel):
    """Update strategy schema."""

    name: Optional[str] = None
    description: Optional[str] = None
    strategy_type: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class StrategyResponse(StrategyBase):
    """Strategy response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: Optional[datetime] = None


class StrategyListResponse(BaseModel):
    """Strategy list response."""

    items: List[StrategyResponse]
