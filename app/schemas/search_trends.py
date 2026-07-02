"""Search-trends Pydantic schemas.

Used by the API layer to serialize ORM rows for the ``search_trends``
table (Baidu + Google Trends observations).
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SearchTrendBase(BaseModel):
    """Common fields exposed in list / detail responses."""

    keyword: str
    region: str = "CN"
    source: str = Field(..., description="数据来源: baidu / google")
    trade_date: date
    value: int
    is_partial: bool = False
    proxy_quality: str = "high"
    category: str | None = None


class SearchTrendOut(SearchTrendBase):
    """Search trend record as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    fetched_at: datetime | None = None
    created_at: datetime | None = None


class SearchTrendListResponse(BaseModel):
    """Paginated list response."""

    items: list[SearchTrendOut]
    total: int
    page: int
    page_size: int


class SearchTrendDashboardResponse(BaseModel):
    """Latest-day dashboard summary.

    Each section is best-effort: a missing section means no fresh data
    was available for that source on the latest date.
    """

    as_of: date | None = Field(None, description="最新观察日期")
    baidu: dict[str, Any] = Field(
        default_factory=dict,
        description="百度: { trade_date, count, top_keywords }",
    )
    google: dict[str, Any] = Field(
        default_factory=dict,
        description="Google: { trade_date, count, top_keywords }",
    )


class SearchTrendCompareResponse(BaseModel):
    """Compare time-series for one keyword across sources."""

    keyword: str
    series: list[SearchTrendOut]