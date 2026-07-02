"""Cninfo periodic report API endpoints.

Five endpoints (matching the listing-events style):

    GET    /cninfo-reports                       — paginated list
    GET    /cninfo-reports/coverage              — coverage summary
    GET    /cninfo-reports/{id}                  — single report + preview
    GET    /cninfo-reports/{id}/download         — admin-only PDF download
    POST   /cninfo-reports/refresh               — admin-only manual refresh
"""

import logging
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.database import SessionLocal
from app.core.redis_client import redis_lock
from app.data.pipelines.cninfo_reports import CninfoReportsPipeline
from app.schemas.auth import UserResponse
from app.schemas.cninfo_report import (
    CninfoReportCoverage,
    CninfoReportDetail,
    CninfoReportListResponse,
)
from app.services.cninfo_report_service import CninfoReportService

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["CNINFO Reports"],
    dependencies=[Depends(get_current_user)],
)


def get_cninfo_report_service(db: Session = Depends(get_db)) -> CninfoReportService:
    """Provide a CninfoReportService instance with a DB session."""
    return CninfoReportService(db)


@router.get("", response_model=CninfoReportListResponse)
def list_cninfo_reports(
    ts_code: str | None = None,
    fiscal_year: int | None = None,
    fiscal_quarter: int | None = Query(None, ge=1, le=4),
    adjunct_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    has_text: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: CninfoReportService = Depends(get_cninfo_report_service),
) -> CninfoReportListResponse:
    """Return a paginated list of cninfo periodic reports."""
    return service.list_reports(
        ts_code=ts_code,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        adjunct_type=adjunct_type,
        start_date=start_date,
        end_date=end_date,
        has_text=has_text,
        page=page,
        page_size=page_size,
    )


@router.get("/coverage", response_model=CninfoReportCoverage)
def get_cninfo_coverage(
    service: CninfoReportService = Depends(get_cninfo_report_service),
) -> CninfoReportCoverage:
    """Return coverage summary (totals + breakdowns)."""
    return service.get_coverage()


@router.get("/{report_id}", response_model=CninfoReportDetail)
def get_cninfo_report(
    report_id: int,
    service: CninfoReportService = Depends(get_cninfo_report_service),
) -> CninfoReportDetail:
    """Return a single report with extracted-text preview."""
    report = service.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Cninfo report not found")
    return report


@router.get("/{report_id}/download")
def download_cninfo_report(
    report_id: int,
    _admin: UserResponse = Depends(
        __import__("app.api.deps", fromlist=["require_admin"]).require_admin
    ),
    service: CninfoReportService = Depends(get_cninfo_report_service),
) -> FileResponse:
    """Download the PDF for one report (admin only).

    Streams the file from local storage.  If the PDF has not been
    downloaded yet, the service is asked to fetch it on the spot.
    """
    report = service.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Cninfo report not found")

    file_path = report.get("file_path")
    if not file_path:
        # Lazy download on first request.
        path = service.download_pdf(report_id)
        if path is None:
            raise HTTPException(
                status_code=502,
                detail="Failed to download PDF from cninfo",
            )
        file_path = str(path)

    path_obj = Path(file_path)
    if not path_obj.exists():
        raise HTTPException(status_code=410, detail="PDF file missing on disk")

    return FileResponse(
        path=str(path_obj),
        media_type="application/pdf",
        filename=path_obj.name,
    )


@router.post("/refresh", status_code=202)
def refresh_cninfo_reports(
    _admin: UserResponse = Depends(
        __import__("app.api.deps", fromlist=["require_admin"]).require_admin
    ),
) -> dict[str, str]:
    """Manually trigger a cninfo refresh (admin only)."""
    with redis_lock("cninfo_reports_refresh", expire_seconds=3600) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=409,
                detail="Cninfo refresh already in progress",
            )
        db = SessionLocal()
        try:
            pipeline = CninfoReportsPipeline(db)
            result = pipeline.run_with_retry(max_attempts=1)
            if not result.success:
                raise HTTPException(
                    status_code=500,
                    detail=f"Cninfo refresh failed: {result.error}",
                )
            return {
                "status": "ok",
                "records": str(result.records),
            }
        finally:
            db.close()