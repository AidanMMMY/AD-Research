"""Sector rotation API routes."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_sector_rotation_service
from app.schemas.sector_rotation import (
    SectorConstituentsResponse,
    SectorListItem,
    SectorListResponse,
    SectorRotationResponse,
)
from app.services.sector_rotation_service import SectorRotationService

router = APIRouter()


@router.get("/sector-rotation", response_model=SectorRotationResponse)
def get_sector_rotation(
    trade_date: date | None = Query(None, description="Analysis date (default: latest)"),
    window_weeks: int = Query(4, ge=1, le=52, description="Momentum window in weeks"),
    classification: Literal["GICS", "SW"] = Query(
        "GICS",
        description="Industry taxonomy: GICS (default, global) or SW (申万2021一级, A股)",
    ),
    service: SectorRotationService = Depends(get_sector_rotation_service),
):
    """Get sector rotation analysis data."""
    result = service.analyze_sectors(
        trade_date=trade_date,
        window_weeks=window_weeks,
        classification=classification,
    )
    return SectorRotationResponse(**result)


@router.get("/sector-rotation/sectors", response_model=SectorListResponse)
def list_sectors(
    classification: Literal["GICS", "SW"] = Query(
        "GICS",
        description="Industry taxonomy: GICS (default) or SW (申万2021一级, A股)",
    ),
    service: SectorRotationService = Depends(get_sector_rotation_service),
):
    """Get all industry sectors with counts."""
    items = service.get_sector_list(classification=classification)
    return SectorListResponse(items=[SectorListItem.model_validate(i) for i in items])


@router.get(
    "/sector-rotation/sectors/{sector}/constituents",
    response_model=SectorConstituentsResponse,
)
def get_sector_constituents(
    sector: str,
    top_n: int = Query(20, ge=1, le=200, description="Max constituents to return (1-200)"),
    trade_date: date | None = Query(None, description="Indicator date (default: latest)"),
    classification: Literal["GICS", "SW"] = Query(
        "GICS",
        description="Industry taxonomy the sector name belongs to: GICS or SW",
    ),
    service: SectorRotationService = Depends(get_sector_rotation_service),
):
    """Top-N instruments inside a single sector (GICS or 申万一级).

    Mixed STOCK + ETF view, weighted by market cap (STOCK) or fund size
    (ETF). Used by the SectorRotation UI's "成份股构成" tab.
    """
    result = service.get_sector_constituents(
        sector=sector, top_n=top_n, trade_date=trade_date, classification=classification
    )
    if result["total_in_sector"] == 0:
        # Surface a 404 when the sector name is unknown to make typos in
        # the URL obvious. Empty sectors still resolve to 200 with
        # count=0.
        known = {item["sector"] for item in service.get_sector_list(classification)}
        if sector not in known:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown sector '{sector}'. Known sectors: {sorted(known)}",
            )
    return SectorConstituentsResponse(**result)
