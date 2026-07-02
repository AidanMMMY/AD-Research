"""Search-trends API routes.

Exposes:
  - GET  ``/search-trends``             paginated list with filters
  - GET  ``/search-trends/dashboard``   latest-day summary
  - GET  ``/search-trends/compare``     compare one keyword across sources
  - POST ``/search-trends/refresh``     admin-only ETL refresh
"""

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.core.database import SessionLocal
from app.core.redis_client import redis_lock
from app.data.pipelines.search_trends import SearchTrendsPipeline
from app.models.search_trends import SearchTrend
from app.schemas.auth import UserResponse
from app.schemas.search_trends import (
    SearchTrendCompareResponse,
    SearchTrendDashboardResponse,
    SearchTrendListResponse,
    SearchTrendOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/search-trends",
    tags=["Search Trends"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=SearchTrendListResponse)
def list_search_trends(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source: str | None = Query(None, description="baidu / google"),
    region: str | None = Query(None),
    category: str | None = Query(None, description="indices / stocks / macro"),
    keyword: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    sort_by: str = Query("trade_date"),
    sort_dir: str = Query("desc"),
    db: Session = Depends(get_db),
) -> SearchTrendListResponse:
    """Return a paginated list of search-trend observations."""
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20
    sort_dir_norm = sort_dir.lower() if sort_dir.lower() in ("asc", "desc") else "desc"
    sortable = {"trade_date", "value", "fetched_at", "created_at"}
    if sort_by not in sortable:
        sort_by = "trade_date"

    stmt = select(SearchTrend)
    count_stmt = select(func.count(SearchTrend.id))

    if source:
        stmt = stmt.where(SearchTrend.source == source)
        count_stmt = count_stmt.where(SearchTrend.source == source)
    if region:
        stmt = stmt.where(SearchTrend.region == region)
        count_stmt = count_stmt.where(SearchTrend.region == region)
    if category:
        stmt = stmt.where(SearchTrend.category == category)
        count_stmt = count_stmt.where(SearchTrend.category == category)
    if keyword:
        stmt = stmt.where(SearchTrend.keyword == keyword)
        count_stmt = count_stmt.where(SearchTrend.keyword == keyword)
    if start_date:
        stmt = stmt.where(SearchTrend.trade_date >= start_date)
        count_stmt = count_stmt.where(SearchTrend.trade_date >= start_date)
    if end_date:
        stmt = stmt.where(SearchTrend.trade_date <= end_date)
        count_stmt = count_stmt.where(SearchTrend.trade_date <= end_date)

    sort_col = getattr(SearchTrend, sort_by)
    stmt = stmt.order_by(
        sort_col.desc() if sort_dir_norm == "desc" else sort_col.asc()
    )

    total = db.execute(count_stmt).scalar() or 0
    rows = db.execute(
        stmt.offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()

    return {
        "items": [_to_out(r) for r in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


@router.get("/dashboard", response_model=SearchTrendDashboardResponse)
def get_search_trends_dashboard(
    db: Session = Depends(get_db),
) -> SearchTrendDashboardResponse:
    """Return latest-day summary for the dashboard."""
    today = date.today()
    summary: dict[str, Any] = {"as_of": None}

    for source in ("baidu", "google"):
        try:
            latest_day = db.execute(
                select(func.max(SearchTrend.trade_date)).where(SearchTrend.source == source)
            ).scalar()
            if latest_day is None:
                summary[source] = {}
                continue
            top_rows = db.execute(
                select(SearchTrend)
                .where(SearchTrend.source == source, SearchTrend.trade_date == latest_day)
                .order_by(desc(SearchTrend.value))
                .limit(10)
            ).scalars().all()
            count = db.execute(
                select(func.count(SearchTrend.id)).where(
                    SearchTrend.source == source, SearchTrend.trade_date == latest_day
                )
            ).scalar() or 0
            summary[source] = {
                "trade_date": latest_day.isoformat(),
                "count": int(count),
                "top_keywords": [_to_out(r) for r in top_rows],
            }
            # Capture as_of = max(baidu_latest, google_latest)
            cur = summary.get("as_of")
            if cur is None or latest_day > cur:
                summary["as_of"] = latest_day
        except Exception as exc:  # noqa: BLE001
            logger.warning("search_trends.dashboard %s failed: %s", source, exc)
            summary[source] = {}

    return SearchTrendDashboardResponse(**summary)


@router.get("/compare", response_model=SearchTrendCompareResponse)
def compare_search_trends(
    keyword: str = Query(..., min_length=1),
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> SearchTrendCompareResponse:
    """Return the time-series for one keyword across both sources."""
    from datetime import timedelta

    cutoff = date.today() - timedelta(days=days)
    rows = db.execute(
        select(SearchTrend)
        .where(SearchTrend.keyword == keyword, SearchTrend.trade_date >= cutoff)
        .order_by(SearchTrend.trade_date.asc())
    ).scalars().all()
    return SearchTrendCompareResponse(
        keyword=keyword,
        series=[_to_out(r) for r in rows],
    )


@router.post("/refresh", status_code=202)
def refresh_search_trends(
    _admin: UserResponse = Depends(require_admin),
) -> dict[str, Any]:
    """Trigger a full search-trends refresh (admin only)."""
    with redis_lock("search_trends_refresh", expire_seconds=1800) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=409,
                detail="Search-trends refresh already in progress",
            )
        db = SessionLocal()
        try:
            pipeline = SearchTrendsPipeline(db)
            result = pipeline.run_with_retry(max_attempts=1)
            if not result.success:
                raise HTTPException(
                    status_code=500,
                    detail=f"Search-trends refresh failed: {result.error}",
                )
            return {
                "status": "ok",
                "records": str(result.records),
                "warnings": result.warnings,
            }
        finally:
            db.close()


def _to_out(row: SearchTrend) -> SearchTrendOut:
    return SearchTrendOut(
        id=row.id,
        keyword=row.keyword,
        region=row.region,
        source=row.source,
        trade_date=row.trade_date,
        value=int(row.value or 0),
        is_partial=bool(row.is_partial),
        proxy_quality=row.proxy_quality,
        category=row.category,
        fetched_at=row.fetched_at,
        created_at=row.created_at,
    )