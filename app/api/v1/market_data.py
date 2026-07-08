"""Market data API routes.

Provides endpoints for historical OHLCV bars and market snapshots.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user, get_market_data_service
from app.schemas.market_data import MarketDataHistoryResponse, MarketSnapshotResponse
from app.services.market_data_service import MarketDataService

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/{code}/history", response_model=MarketDataHistoryResponse)
def get_history(
    code: str,
    start: date = Query(None, alias="start_date"),
    end: date = Query(None, alias="end_date"),
    limit: int = Query(None),
    adjusted: bool = Query(False, description="前复权（针对 ETF / 现金分红型标的）"),
    service: MarketDataService = Depends(get_market_data_service),
):
    """Get historical OHLCV bars for an instrument.

    When ``adjusted=true`` the response includes ``adj_factor`` and
    ``adj_close`` fields. ``adj_close = close * adj_factor`` represents
    the forward-adjusted close suitable for plotting continuous K-lines
    across dividend events.
    """
    return service.get_history(
        code, start=start, end=end, limit=limit, adjusted=adjusted
    )


@router.get("/snapshot", response_model=MarketSnapshotResponse)
def get_snapshot(
    codes: list[str] = Query(...),
    service: MarketDataService = Depends(get_market_data_service),
):
    """Get the latest market snapshot for a list of ETF codes."""
    return service.get_snapshot(codes)
