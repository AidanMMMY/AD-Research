"""Research-report API routes.

Endpoints (mounted under ``/api/v1/research-reports``):

  * ``GET    /``                       — paginated list with filters
  * ``GET    /facets``                 — distinct values for dropdowns
  * ``GET    /{id}``                   — single report detail
  * ``POST   /refresh``                — admin-only manual refresh
  * ``POST   /{id}/summarize``         — authenticated on-demand summary,
                                         rate-limited per user per day
"""

import logging
from datetime import date

import redis
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import (
    get_current_user,
    get_research_report_service,
    require_admin,
)
from app.config import get_settings
from app.core.database import SessionLocal
from app.core.redis_client import get_redis_client, redis_lock
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
    rating: str | None = Query(None, description="Filter by analyst rating (e.g. 买入, 增持)"),
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
        rating=rating,
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
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, str]:
    """Run DeepSeek summary for a single report.

    Open to any authenticated user, but rate-limited to
    ``research_report_summarize_daily_limit`` calls per user per
    calendar day (resets at 00:00 local).  The 120s Redis lock is kept
    so concurrent jobs across users are still serialized.
    """
    # Per-user daily counter. Fail-open if Redis is unavailable so the
    # feature stays usable during a Redis outage.
    daily_limit = get_settings().research_report_summarize_daily_limit
    today = date.today().isoformat()
    counter_key = (
        f"research_reports_summarize_user:{current_user.id}:{today}"
    )
    try:
        redis_client = get_redis_client()
        current = redis_client.incr(counter_key)
        if current == 1:
            # 86400s = 24h. Good enough for "until midnight" semantics
            # without needing a per-day TTL calculation.
            redis_client.expire(counter_key, 86400)
        if current > daily_limit:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"今日摘要生成次数已达上限（{daily_limit} 次），"
                    "明天 0 点重置"
                ),
            )
    except redis.RedisError as exc:
        # Redis down — log and let the request through rather than
        # blocking all summarize calls.
        logger.warning(
            "research_reports summarize rate-limit unavailable (Redis error): %s",
            exc,
        )
    except HTTPException:
        raise
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