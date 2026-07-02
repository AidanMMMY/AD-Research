"""Research-report API routes.

Endpoints (mounted under ``/api/v1/research-reports``):

  * ``GET    /``                       — paginated list with filters
  * ``GET    /facets``                 — distinct values for dropdowns
  * ``GET    /{id}``                   — single report detail
  * ``POST   /refresh``                — admin-only manual refresh
  * ``POST   /{id}/summarize``         — admin-only on-demand summary
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import (
    get_current_user,
    get_research_report_service,
    require_admin,
)
from app.core.database import SessionLocal
from app.core.redis_client import redis_lock
from app.data.pipelines.research_reports import ResearchReportsPipeline
from app.schemas.auth import UserResponse
from app.schemas.research_report import (
    ResearchReportDetail,
    ResearchReportFacetsResponse,
    ResearchReportListResponse,
)
from app.services.research_report_service import ResearchReportService

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Research Reports"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=ResearchReportListResponse)
def list_research_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ts_code: str | None = None,
    industry: str | None = None,
    org_name: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    has_summary: bool | None = Query(None),
    sort_by: str = Query("publish_date"),
    sort_dir: str = Query("desc"),
    service: ResearchReportService = Depends(get_research_report_service),
) -> ResearchReportListResponse:
    """Return a paginated list of research reports with filters."""
    return service.list_reports(
        page=page,
        page_size=page_size,
        ts_code=ts_code,
        industry=industry,
        org_name=org_name,
        start_date=start_date,
        end_date=end_date,
        has_summary=has_summary,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@router.get("/facets", response_model=ResearchReportFacetsResponse)
def get_research_report_facets(
    service: ResearchReportService = Depends(get_research_report_service),
) -> ResearchReportFacetsResponse:
    """Return distinct values for industries, orgs, ratings."""
    facets = service.get_facets()
    return ResearchReportFacetsResponse(
        industries=facets.get("industries", []),
        orgs=facets.get("orgs", []),
        ratings=facets.get("ratings", []),
    )


@router.get("/{report_id}", response_model=ResearchReportDetail)
def get_research_report(
    report_id: int,
    service: ResearchReportService = Depends(get_research_report_service),
) -> ResearchReportDetail:
    """Return a single research report detail by id."""
    report = service.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Research report not found")
    return report


@router.post("/refresh", status_code=202)
def refresh_research_reports(
    _admin: UserResponse = Depends(require_admin),
) -> dict[str, str]:
    """Manually trigger a refresh of the research-reports table (admin only)."""
    with redis_lock("research_reports_refresh", expire_seconds=1800) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=409,
                detail="Research-reports refresh already in progress",
            )
        db = SessionLocal()
        try:
            pipeline = ResearchReportsPipeline(db)
            result = pipeline.run_with_retry(max_attempts=1)
            if not result.success:
                raise HTTPException(
                    status_code=500,
                    detail=f"Research-reports refresh failed: {result.error}",
                )
            return {
                "status": "ok",
                "records": str(result.records),
            }
        finally:
            db.close()


@router.post("/{report_id}/summarize", status_code=202)
def summarize_research_report(
    report_id: int,
    _admin: UserResponse = Depends(require_admin),
) -> dict[str, str]:
    """Run DeepSeek summary for a single report (admin only)."""
    with redis_lock("research_reports_summarize", expire_seconds=120) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=409,
                detail="Research-reports summarize already in progress",
            )
        db = SessionLocal()
        try:
            service = ResearchReportService(db)
            try:
                summary = service.summarize_with_deepseek(report_id)
            except ValueError:
                raise HTTPException(
                    status_code=404, detail="Research report not found"
                )
            return {
                "status": "ok",
                "id": str(report_id),
                "summary": summary or "",
            }
        finally:
            db.close()