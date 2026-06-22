"""Market data API routes.

Provides endpoints for historical OHLCV bars and market snapshots.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_market_data_service
from app.schemas.market_data import MarketDataHistoryResponse, MarketSnapshotResponse
from app.services.market_data_service import MarketDataService

router = APIRouter()


@router.get("/{code}/history", response_model=MarketDataHistoryResponse)
def get_history(
    code: str,
    start: date = Query(None, alias="start_date"),
    end: date = Query(None, alias="end_date"),
    limit: int = Query(None),
    service: MarketDataService = Depends(get_market_data_service),
):
    """Get historical OHLCV bars for an ETF."""
    return service.get_history(code, start=start, end=end, limit=limit)


@router.get("/snapshot", response_model=MarketSnapshotResponse)
def get_snapshot(
    codes: list[str] = Query(...),
    service: MarketDataService = Depends(get_market_data_service),
):
    """Get the latest market snapshot for a list of ETF codes."""
    return service.get_snapshot(codes)
