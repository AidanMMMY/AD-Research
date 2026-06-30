"""A-share individual stock API routes.

Provides endpoints for listing, filtering, and retrieving A-share stock
information and financial statement history.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_etf_service, get_stock_fundamental_service
from app.schemas.etf import ETFInfoResponse, ETFListResponse, ETFFilterParams
from app.schemas.stock_financials import StockFinancialsResponse
from app.services.etf_service import ETFService
from app.services.stock_fundamental_service import StockFundamentalService

router = APIRouter()


@router.get("", response_model=ETFListResponse)
def list_stocks(
    market: str = Query(None),
    category: str = Query(None),
    search: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    service: ETFService = Depends(get_etf_service),
):
    """List A-share individual stocks with optional filtering and pagination."""
    params = ETFFilterParams(
        market=market,
        category=category,
        instrument_type="STOCK",
        search=search,
        page=page,
        page_size=page_size,
    )
    return service.list_etfs(params)


@router.get("/{code}/financials", response_model=StockFinancialsResponse)
def get_stock_financials(
    code: str,
    limit: int = Query(20, ge=1, le=100),
    service: StockFundamentalService = Depends(get_stock_fundamental_service),
):
    """Get historical income statements and balance sheets for a stock."""
    result = service.get_financials_history(code, limit=limit)
    return result


@router.get("/{code}", response_model=ETFInfoResponse)
def get_stock(code: str, service: ETFService = Depends(get_etf_service)):
    """Get a single A-share stock by its code."""
    stock = service.get_etf(code)
    if not stock or stock.instrument_type != "STOCK":
        raise HTTPException(status_code=404, detail=f"Stock {code} not found")
    return stock
