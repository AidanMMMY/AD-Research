"""ETF API routes.

Provides endpoints for listing, filtering, and retrieving ETF basic information.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_etf_service
from app.schemas.etf import ETFFilterParams, ETFInfoResponse, ETFListResponse
from app.services.etf_service import ETFService

router = APIRouter()


@router.get("", response_model=ETFListResponse)
def list_etfs(
    market: str = Query(None),
    category: str = Query(None),
    search: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    service: ETFService = Depends(get_etf_service),
):
    """List ETFs with optional filtering and pagination."""
    params = ETFFilterParams(
        market=market, category=category, search=search, page=page, page_size=page_size
    )
    return service.list_etfs(params)


@router.get("/{code}", response_model=ETFInfoResponse)
def get_etf(code: str, service: ETFService = Depends(get_etf_service)):
    """Get a single ETF by its code."""
    etf = service.get_etf(code)
    if not etf:
        raise HTTPException(status_code=404, detail=f"ETF {code} not found")
    return etf


@router.get("/categories/list")
def list_categories(service: ETFService = Depends(get_etf_service)):
    """List all distinct ETF categories."""
    return {"categories": service.get_categories()}


@router.get("/markets/list")
def list_markets(service: ETFService = Depends(get_etf_service)):
    """List all distinct ETF markets."""
    return {"markets": service.get_markets()}
