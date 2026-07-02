"""Research-report Pydantic schemas."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResearchReportBase(BaseModel):
    """Fields common to all research-report schemas."""

    ts_code: str
    name: str
    title: str
    org_name: str
    industry: str | None = None
    publish_date: date
    rating: str | None = None
    pdf_url: str | None = None
    target_price: float | None = None
    current_price_at_publish: float | None = None
    source: str = "eastmoney"


class ResearchReportOut(ResearchReportBase):
    """List-view schema for a research report."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    summary: str | None = None
    key_points: list[str] | None = None
    fetched_at: datetime | None = None
    updated_at: datetime | None = None


class ResearchReportDetail(ResearchReportOut):
    """Detail-view schema including the raw upstream payload."""

    raw_payload: dict[str, Any] | None = None
    created_at: datetime | None = None


class ResearchReportListResponse(BaseModel):
    """Paginated research-report list response."""

    items: list[ResearchReportOut]
    total: int
    page: int
    page_size: int


class ResearchReportFacetsResponse(BaseModel):
    """Distinct values for the three filter dimensions."""

    industries: list[str] = Field(default_factory=list)
    orgs: list[str] = Field(default_factory=list)
    ratings: list[str] = Field(default_factory=list)
