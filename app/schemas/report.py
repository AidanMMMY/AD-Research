"""Report generation Pydantic schemas.

Provides request/response models for report generation, status tracking,
and report listing operations.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

# ------------------------------------------------------------------
# Report generation request
# ------------------------------------------------------------------

class ReportGenerateRequest(BaseModel):
    """Request model for triggering report generation."""

    report_type: str = "pool_weekly"
    pool_id: int | None = None
    format: str = "html"
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
