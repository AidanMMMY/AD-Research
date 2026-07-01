"""Listing / IPO event Pydantic schemas."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ListingEventBase(BaseModel):
    """Fields common to all listing event schemas."""

    ts_code: str
    sub_code: str | None = None
    name: str
    market: str | None = None
    board: str | None = None
    industry: str | None = None
    issue_date: date | None = None
    list_date: date | None = None
    issue_price: float | None = None
    pe_ratio: float | None = None
    limit_amount: float | None = None
    funds_raised: float | None = None
    market_amount: float | None = None
    sponsor: str | None = None
    underwriter: str | None = None


class ListingEventOut(ListingEventBase):
    """Listing event response with id and metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    source: str
    fetched_at: datetime | None = None
    updated_at: datetime | None = None


class ListingEventDetail(ListingEventOut):
    """Detail view including the raw upstream payload."""

    raw_payload: dict[str, Any] | None = None
    created_at: datetime | None = None


class ListingEventListResponse(BaseModel):
    """Paginated listing event list response."""

    items: list[ListingEventOut]
    total: int
    page: int
    page_size: int
    updated_at: datetime | None = None


class ListingEventFacetsResponse(BaseModel):
    """Distinct values for the four filter dimensions."""

    industries: list[str] = Field(default_factory=list)
    boards: list[str] = Field(default_factory=list)
    markets: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
