"""Listing / IPO event API routes."""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user, get_listing_event_service, require_admin
from app.core.database import SessionLocal
from app.core.redis_client import redis_lock
from app.data.pipelines.listing_events import ListingEventsPipeline
from app.schemas.auth import UserResponse
from app.schemas.listing_event import (
    ListingEventDetail,
    ListingEventFacetsResponse,
    ListingEventListResponse,
)
from app.services.listing_event_service import ListingEventService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/listing-events",
    tags=["Listing Events"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=ListingEventListResponse)
def list_listing_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    board: list[str] | None = Query(None),
    market: list[str] | None = Query(None),
    status: list[str] | None = Query(None, alias="status"),
    industry: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    date_field: str = Query("list_date"),
    q: str | None = None,
    sort_by: str = Query("list_date"),
    sort_dir: str = Query("desc"),
    service: ListingEventService = Depends(get_listing_event_service),
) -> ListingEventListResponse:
    """Return a paginated list of listing / IPO events with filters."""
    return service.list_events(
        page=page,
        page_size=page_size,
        boards=board,
        markets=market,
        statuses=status,
        industry=industry,
        start_date=start_date,
        end_date=end_date,
        date_field=date_field,
        q=q,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@router.get("/facets", response_model=ListingEventFacetsResponse)
def get_listing_event_facets(
    service: ListingEventService = Depends(get_listing_event_service),
) -> ListingEventFacetsResponse:
    """Return distinct filter values for the listing-events UI."""
    return service.get_facets()


@router.get("/{event_id}", response_model=ListingEventDetail)
def get_listing_event(
    event_id: int,
    service: ListingEventService = Depends(get_listing_event_service),
) -> ListingEventDetail:
    """Return a single listing event by id."""
    event = service.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Listing event not found")
    return event


@router.post("/refresh", status_code=202)
def refresh_listing_events(
    _admin: UserResponse = Depends(require_admin),
) -> dict[str, str]:
    """Manually trigger a refresh of the listing events table (admin only)."""
    with redis_lock("listing_events_refresh", expire_seconds=600) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=409,
                detail="Listing-events refresh already in progress",
            )
        db = SessionLocal()
        try:
            pipeline = ListingEventsPipeline(db)
            result = pipeline.run_with_retry(max_attempts=1)
            if not result.success:
                raise HTTPException(
                    status_code=500,
                    detail=f"Listing-events refresh failed: {result.error}",
                )
            return {
                "status": "ok",
                "records": str(result.records),
            }
        finally:
            db.close()
