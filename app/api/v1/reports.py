"""Report generation API routes.

Provides endpoints for listing reports, triggering generation,
checking status, and downloading generated report files.
"""

import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.api.deps import get_current_user, get_report_service
from app.schemas.report import (
    ReportGenerateRequest,
    ReportResponse,
    ReportStatusResponse,
)
from app.services.report_service import ReportService

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[ReportResponse])
def list_reports(
    report_type: str | None = Query(None, description="Filter by report type"),
    pool_id: int | None = Query(None, description="Filter by pool ID"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of results"),
    service: ReportService = Depends(get_report_service),
):
    """List generated reports with optional filtering.

    Returns reports ordered by creation time (newest first).
    """
    reports = service.get_reports(
        report_type=report_type,
        pool_id=pool_id,
        limit=limit,
    )
    return reports


@router.post("/generate", response_model=ReportResponse, status_code=201)
def generate_report(
    request: ReportGenerateRequest,
    service: ReportService = Depends(get_report_service),
):
    """Trigger report generation for a pool.

    Creates a report metadata record, generates the report content
    (HTML or Markdown), and saves it to disk.
    """
    if request.pool_id is None:
        raise HTTPException(status_code=400, detail="pool_id is required")

    metadata = service.generate_pool_report(
        pool_id=request.pool_id,
        report_type=request.report_type,
        format=request.format,
        template_id=request.template_id,
    )
    return metadata


@router.get("/{report_id}/status", response_model=ReportStatusResponse)
def get_report_status(
    report_id: int,
    service: ReportService = Depends(get_report_service),
):
    """Get the generation status of a report."""
    report = service.get_report_status(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return report


@router.get("/{report_id}/download")
def download_report(
    report_id: int,
    service: ReportService = Depends(get_report_service),
):
    """Download a generated report file.

    Returns the file as a FileResponse with appropriate content type.
    """
    report = service.get_report_status(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

    if report.status != "done":
        raise HTTPException(
            status_code=400,
            detail=f"Report is not ready (status: {report.status})",
        )

    if not report.file_path or not os.path.exists(report.file_path):
        raise HTTPException(status_code=404, detail="Report file not found")

    media_type = "text/html" if report.format == "html" else "text/markdown"
    return FileResponse(
        path=report.file_path,
        media_type=media_type,
        filename=f"report_{report.report_type}_{report.pool_id}_{report.report_date}.{report.format}",
    )
