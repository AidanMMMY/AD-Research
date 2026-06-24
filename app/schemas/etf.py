from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ETFInfoBase(BaseModel):
    code: str
    name: str
    exchange: str | None = None
    market: str | None = None
    category: str | None = None
    sub_category: str | None = None
    manager: str | None = None
    currency: str = "CNY"
    is_qdii: bool = False
    underlying_index: str | None = None
    inception_date: date | None = None
    status: str = "active"


class ETFInfoResponse(ETFInfoBase):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    fund_manager: str | None = None
    fund_size: float | None = None
    instrument_type: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    country: str | None = None


class ETFListResponse(BaseModel):
    items: list[ETFInfoResponse]
    total: int
    page: int
    page_size: int


class ETFFilterParams(BaseModel):
    market: str | None = None
    category: str | None = None
    instrument_type: str | None = None
    search: str | None = None
    page: int = 1
    page_size: int = 50
