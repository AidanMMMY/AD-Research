"""A-share micro-structure data API routes.

Exposes:
  - GET  ``/microstructure/lhb``                  paginated 龙虎榜 list
  - GET  ``/microstructure/hsgt``                 recent HSGT flows
  - GET  ``/microstructure/margin``               paginated 融资融券 list
  - GET  ``/microstructure/restricted-releases``  paginated 限售解禁 list
  - GET  ``/microstructure/summary``              dashboard summary
  - GET  ``/microstructure/facets``               distinct filter values
  - POST ``/microstructure/refresh``              admin-only ETL refresh
"""

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.core.database import SessionLocal
from app.core.redis_client import redis_lock
from app.data.pipelines.microstructure import MicrostructurePipeline
from app.schemas.auth import UserResponse
from app.schemas.microstructure import (
    LhbRecordListResponse,
    MarginBalanceListResponse,
    MicrostructureSummaryResponse,
    RestrictedReleaseListResponse,
)
from app.services import microstructure_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/microstructure",
    tags=["Microstructure"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/lhb", response_model=LhbRecordListResponse)
def list_lhb(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ts_code: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    sort_dir: str = Query("desc"),
    db: Session = Depends(get_db),
) -> LhbRecordListResponse:
    """Return a paginated list of 龙虎榜 (LHB) records."""
    return svc.list_lhb(
        db,
        page=page,
        page_size=page_size,
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
        sort_dir=sort_dir,
    )


@router.get("/hsgt")
def list_hsgt(
    days: int = Query(30, ge=1, le=365),
    flow_type: str | None = Query(None, description="北向 / 沪股通 / 深股通"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return recent 沪深港通 (HSGT) flow records."""
    return svc.list_hsgt(db, days=days, flow_type=flow_type)


@router.get("/margin", response_model=MarginBalanceListResponse)
def list_margin(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ts_code: str | None = None,
    exchange: str | None = Query(None, description="SSE / SZSE"),
    start_date: date | None = None,
    end_date: date | None = None,
    sort_dir: str = Query("desc"),
    db: Session = Depends(get_db),
) -> MarginBalanceListResponse:
    """Return a paginated list of 融资融券 (margin) balances."""
    return svc.list_margin(
        db,
        page=page,
        page_size=page_size,
        ts_code=ts_code,
        exchange=exchange,
        start_date=start_date,
        end_date=end_date,
        sort_dir=sort_dir,
    )


@router.get("/restricted-releases", response_model=RestrictedReleaseListResponse)
def list_restricted_releases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ts_code: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    sort_dir: str = Query("asc"),
    db: Session = Depends(get_db),
) -> RestrictedReleaseListResponse:
    """Return a paginated list of 限售解禁 (restricted-share release) events."""
    return svc.list_restricted_releases(
        db,
        page=page,
        page_size=page_size,
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
        sort_dir=sort_dir,
    )


@router.get("/summary", response_model=MicrostructureSummaryResponse)
def get_microstructure_summary(
    db: Session = Depends(get_db),
) -> MicrostructureSummaryResponse:
    """Return latest-day micro-structure summary (dashboard use)."""
    return svc.get_summary(db)


@router.get("/facets")
def get_microstructure_facets(
    db: Session = Depends(get_db),
) -> dict[str, list[str]]:
    """Return distinct filter values (exchanges, etc.)."""
    return svc.get_facets(db)


@router.post("/refresh", status_code=202)
def refresh_microstructure(
    _admin: UserResponse = Depends(require_admin),
) -> dict[str, Any]:
    """Trigger a full micro-structure refresh (admin only)."""
    with redis_lock("microstructure_refresh", expire_seconds=3600) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=409,
                detail="Microstructure refresh already in progress",
            )
        db = SessionLocal()
        try:
            pipeline = MicrostructurePipeline(db)
            result = pipeline.run_with_retry(max_attempts=1)
            if not result.success:
                raise HTTPException(
                    status_code=500,
                    detail=f"Microstructure refresh failed: {result.error}",
                )
            return {
                "status": "ok",
                "records": str(result.records),
                "warnings": result.warnings,
            }
        finally:
            db.close()