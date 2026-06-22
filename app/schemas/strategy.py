"""Strategy Pydantic schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class StrategyTemplate(BaseModel):
    """Preset strategy template."""

    name: str
    description: str
    strategy_type: str
    params: dict[str, Any]


class StrategyBase(BaseModel):
    """Base strategy schema."""

    name: str
    description: str | None = None
    strategy_type: str
    params: dict[str, Any]
    is_active: bool = True


class StrategyCreate(StrategyBase):
    """Create strategy schema."""

    pass


class StrategyUpdate(BaseModel):
    """Update strategy schema."""

    name: str | None = None
    description: str | None = None
    strategy_type: str | None = None
    params: dict[str, Any] | None = None
    is_active: bool | None = None


class StrategyResponse(StrategyBase):
    """Strategy response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime | None = None


class StrategyListResponse(BaseModel):
    """Strategy list response."""

    items: list[StrategyResponse]
