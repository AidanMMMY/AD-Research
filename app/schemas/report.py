"""Report generation Pydantic schemas.

Provides request/response models for report generation, status tracking,
and report listing operations.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ------------------------------------------------------------------
# Report generation request
# ------------------------------------------------------------------

# ``report_type`` and ``format`` are interpolated into the output filename
# (report_service.generate_pool_report). They are allowlisted here so a
# malicious value such as ``../../tmp/pwn`` can never escape the reports
# directory (path-traversal fix, 2026-08-06). Extend the pattern when new
# report types ship — keep it restricted to word chars / dash / underscore.
_REPORT_TYPE_PATTERN = r"^[A-Za-z0-9_-]{1,50}$"
_REPORT_FORMATS = ("html", "markdown")


class ReportGenerateRequest(BaseModel):
    """Request model for triggering report generation."""

    report_type: str = Field(
        default="pool_weekly",
        pattern=_REPORT_TYPE_PATTERN,
        description="Report type; allowlisted to [A-Za-z0-9_-] to prevent path traversal",
    )
    pool_id: int | None = None
    format: Literal["html", "markdown"] = "html"
    template_id: int | None = None


# ------------------------------------------------------------------
# Report response models
# ------------------------------------------------------------------

class ReportResponse(BaseModel):
    """Response model for a generated report."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    report_type: str
    report_date: date
    pool_id: int | None = None
    status: str
    format: str
    file_path: str | None = None
    file_size: int | None = None
    created_at: datetime | None = None


class ReportStatusResponse(BaseModel):
    """Response model for report generation status."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    file_path: str | None = None
    file_size: int | None = None
    error_msg: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
