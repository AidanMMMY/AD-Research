"""Sector rotation API routes."""

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_sector_rotation_service
from app.schemas.sector_rotation import SectorListItem, SectorListResponse, SectorRotationResponse
from app.services.sector_rotation_service import SectorRotationService

router = APIRouter()


@router.get("/sector-rotation", response_model=SectorRotationResponse)
def get_sector_rotation(
    trade_date: date | None = Query(None, description="Analysis date (default: latest)"),
    window_weeks: int = Query(4, ge=1, le=52, description="Momentum window in weeks"),
    service: SectorRotationService = Depends(get_sector_rotation_service),
):
    """Get sector rotation analysis data."""
    result = service.analyze_sectors(trade_date=trade_date, window_weeks=window_weeks)
    return SectorRotationResponse(**result)


@router.get("/sector-rotation/sectors", response_model=SectorListResponse)
def list_sectors(
    service: SectorRotationService = Depends(get_sector_rotation_service),
):
    """Get all ETF categories (sectors) with counts."""
    items = service.get_sector_list()
    return SectorListResponse(items=[SectorListItem.model_validate(i) for i in items])
