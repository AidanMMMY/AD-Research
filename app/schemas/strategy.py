"""Strategy Pydantic schemas."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ParamSpecSchema(BaseModel):
    """Parameter specification schema returned in the strategy catalog."""

    label: str
    type: str
    default: Any
    min: float | None = None
    max: float | None = None
    options: list[str] | None = None
    description: str = ""


class StrategyCatalogItem(BaseModel):
    """Single strategy catalog entry."""

    strategy_type: str
    name: str
    description: str
    family: str
    param_specs: dict[str, ParamSpecSchema]
    min_bars: int


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


class StrategyRunRequest(BaseModel):
    """Request to run a strategy on demand."""

    strategy_type: str
    params: dict[str, Any]
    etf_codes: list[str]
    trade_date: date | None = None
    lookback_days: int = 120


class StrategyRunResponse(BaseModel):
    """Response from running a strategy on demand."""

    signals: list[dict[str, Any]]
    strategy_type: str
    trade_date: str
    instrument_count: int
    signal_count: int
