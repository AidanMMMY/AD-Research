"""Cninfo (巨潮资讯) periodic report Pydantic schemas.

Mirrors the columns on :class:`app.models.cninfo_report.CninfoReport` and
the list / detail / coverage API responses.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# Adjunct type used in the cninfo ``category`` parameter.  Mapped 1:1 to
# ``CninfoReport.adjunct_type``.
AdjunctType = Literal["annual", "semi", "q1", "q3", "other"]


class CninfoReportBase(BaseModel):
    """Fields common to all CninfoReport response schemas.

    Excludes the surrogate ``id``, server-managed timestamps and the raw
    payload / extracted text — those are surfaced only on detail views.
    """

    ts_code: str = Field(..., max_length=20, description="Tushare 证券代码 (e.g. 600519.SH)")
    stock_code: str = Field(..., max_length=20, description="Stock 6-digit code")
    org_id: str | None = Field(None, max_length=32, description="Cninfo orgId")
    sec_code: str | None = Field(None, max_length=32, description="Cninfo secCode")
    announcement_id: str = Field(..., max_length=64, description="Cninfo 公告 ID")
    announcement_title: str = Field(..., max_length=512, description="公告标题")
    adjunct_url: str = Field(..., max_length=512, description="PDF 下载链接")
    file_path: str | None = Field(None, max_length=1024, description="本地 PDF 路径")
    file_size: int | None = Field(None, description="PDF 文件大小 (bytes)")
    announcement_time: datetime = Field(..., description="公告发布时间")
    adjunct_type: str = Field(..., max_length=32, description="附件类型")
    is_periodic: bool = Field(False, description="是否定期报告")
    fiscal_year: int | None = Field(None, description="财年 (e.g. 2025)")
    fiscal_quarter: int | None = Field(None, description="财季: 1=Q1, 2=半年报, 3=Q3, 4=年报")
    source: str = Field("cninfo", max_length=32, description="数据来源")


class CninfoReportOut(CninfoReportBase):
    """Standard response schema with id and extraction metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    extraction_status: str = Field("pending", description="文本提取状态")
    extracted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CninfoReportDetail(CninfoReportOut):
    """Detail view: includes raw upstream payload and a text preview."""

    raw_payload: dict | list | None = Field(
        None, description="上游公告 JSON (parsed)"
    )
    extracted_text_preview: str | None = Field(
        None,
        max_length=500,
        description="PDF 提取出的文本前 500 字",
    )


class CninfoReportListResponse(BaseModel):
    """Paginated list response."""

    items: list[CninfoReportOut]
    total: int
    page: int
    page_size: int
    updated_at: datetime | None = None


class CninfoReportListParams(BaseModel):
    """Query parameters accepted by the list endpoint."""

    ts_code: str | None = None
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None
    adjunct_type: AdjunctType | None = None
    start_date: date | None = None
    end_date: date | None = None
    has_text: bool | None = Field(
        None,
        description="True 过滤已提取的；False 过滤未提取的；None 不过滤",
    )
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class CninfoReportCoverage(BaseModel):
    """Coverage summary for the dashboard."""

    total_reports: int
    stocks_covered: int
    stocks_with_text: int
    fiscal_year_breakdown: dict[int, int]
    adjunct_type_breakdown: dict[str, int]
    updated_at: datetime | None = None