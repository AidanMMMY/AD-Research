"""Technical indicator API routes.

Provides endpoints for latest, historical, and batch technical indicators.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user, get_indicator_service
from app.schemas.indicators import IndicatorBatchResponse, IndicatorResponse
from app.services.indicator_service import IndicatorService

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/{code}", response_model=IndicatorResponse)
def get_latest_indicators(
    code: str,
    service: IndicatorService = Depends(get_indicator_service),
):
    """Get the latest technical indicators for an ETF."""
    result = service.get_latest(code)
    if not result:
        raise HTTPException(status_code=404, detail=f"No indicators found for {code}")
    return result


@router.get("/{code}/history", response_model=list[IndicatorResponse])
def get_indicator_history(
    code: str,
    start: date = Query(None, alias="start_date"),
    end: date = Query(None, alias="end_date"),
    service: IndicatorService = Depends(get_indicator_service),
):
    """Get historical technical indicators for an ETF."""
    return service.get_history(code, start=start, end=end)


@router.get("/batch/latest", response_model=IndicatorBatchResponse)
def get_batch_indicators(
    codes: list[str] = Query(...),
    fields: list[str] = Query(None),
    service: IndicatorService = Depends(get_indicator_service),
):
    """Get the latest indicators for a batch of ETF codes."""
    return service.get_batch(codes, fields=fields)
