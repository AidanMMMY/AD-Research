"""ETF API routes.

Provides endpoints for listing, filtering, and retrieving ETF basic information.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_etf_service
from app.models.etf import ETFInfo, InstrumentDailyBar
from app.schemas.etf import (
    ETFFilterParams,
    ETFInfoResponse,
    ETFListResponse,
    SparklineOut,
)
from app.services.etf_service import ETFService

router = APIRouter(dependencies=[Depends(get_current_user)])


def parse_etf_filter_params(
    market: str = Query(None),
    category: str = Query(None),
    sub_category: str = Query(None),
    sector: str = Query(None),
    industry: str = Query(None),
    country: str = Query(None),
    manager: str = Query(None),
    underlying_index: str = Query(None),
    currency: str = Query(None),
    is_qdii: bool = Query(None),
    status: str = Query(None),
    instrument_type: str = Query(None),
    min_fund_size: float = Query(None),
    max_fund_size: float = Query(None),
    search: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=10000),
) -> ETFFilterParams:
    """Build ETFFilterParams from query string arguments."""
    return ETFFilterParams(
        market=market,
        category=category,
        sub_category=sub_category,
        sector=sector,
        industry=industry,
        country=country,
        manager=manager,
        underlying_index=underlying_index,
        currency=currency,
        is_qdii=is_qdii,
        status=status,
        instrument_type=instrument_type,
        min_fund_size=min_fund_size,
        max_fund_size=max_fund_size,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get("", response_model=ETFListResponse)
def list_etfs(
    params: ETFFilterParams = Depends(parse_etf_filter_params),
    service: ETFService = Depends(get_etf_service),
):
    """List ETFs with optional filtering and pagination."""
    return service.list_etfs(params)


@router.get("/{code}", response_model=ETFInfoResponse)
def get_etf(code: str, service: ETFService = Depends(get_etf_service)):
    """Get a single ETF by its code."""
    etf = service.get_etf(code)
    if not etf:
        raise HTTPException(status_code=404, detail=f"ETF {code} not found")
    return etf


@router.get("/{code}/sparkline", response_model=SparklineOut)
def get_sparkline(
    code: str,
    days: int = Query(30, ge=1, le=365, description="Number of recent trading days to return"),
    db: Session = Depends(get_db),
):
    """Return the most recent ``days`` close prices for ``code``.

    Used for row-level sparkline previews in list pages. The series is
    returned chronologically (oldest -> newest) so the frontend can plot
    directly without reversing.
    """
    instrument = db.query(ETFInfo).filter(ETFInfo.code == code).first()
    if not instrument:
        raise HTTPException(status_code=404, detail=f"ETF {code} not found")

    rows = (
        db.query(InstrumentDailyBar.trade_date, InstrumentDailyBar.close)
        .filter(InstrumentDailyBar.etf_code == code)
        .order_by(InstrumentDailyBar.trade_date.desc())
        .limit(days)
        .all()
    )

    # Reverse so caller gets oldest -> newest (plotting convention).
    rows = list(reversed(rows))

    return SparklineOut(
        code=code,
        days=len(rows),
        points=[float(r.close) for r in rows if r.close is not None],
        dates=[r.trade_date.isoformat() for r in rows],
    )


@router.get("/categories/list")
def list_categories(
    params: ETFFilterParams = Depends(parse_etf_filter_params),
    service: ETFService = Depends(get_etf_service),
):
    """List distinct ETF categories, optionally filtered by market and type."""
    return {"categories": service.get_categories(params)}


@router.get("/sectors/list")
def list_sectors(
    params: ETFFilterParams = Depends(parse_etf_filter_params),
    service: ETFService = Depends(get_etf_service),
):
    """List distinct ETF sectors."""
    return {"sectors": service.get_sectors(params)}


@router.get("/industries/list")
def list_industries(
    params: ETFFilterParams = Depends(parse_etf_filter_params),
    service: ETFService = Depends(get_etf_service),
):
    """List distinct ETF industries."""
    return {"industries": service.get_industries(params)}


@router.get("/sub-categories/list")
def list_sub_categories(
    params: ETFFilterParams = Depends(parse_etf_filter_params),
    service: ETFService = Depends(get_etf_service),
):
    """List distinct ETF sub-categories."""
    return {"sub_categories": service.get_sub_categories(params)}


@router.get("/managers/list")
def list_managers(
    params: ETFFilterParams = Depends(parse_etf_filter_params),
    service: ETFService = Depends(get_etf_service),
):
    """List distinct ETF managers."""
    return {"managers": service.get_managers(params)}


@router.get("/currencies/list")
def list_currencies(
    params: ETFFilterParams = Depends(parse_etf_filter_params),
    service: ETFService = Depends(get_etf_service),
):
    """List distinct ETF currencies."""
    return {"currencies": service.get_currencies(params)}


@router.get("/countries/list")
def list_countries(
    params: ETFFilterParams = Depends(parse_etf_filter_params),
    service: ETFService = Depends(get_etf_service),
):
    """List distinct ETF countries."""
    return {"countries": service.get_countries(params)}


@router.get("/underlying-indices/list")
def list_underlying_indices(
    params: ETFFilterParams = Depends(parse_etf_filter_params),
    service: ETFService = Depends(get_etf_service),
):
    """List distinct underlying indices."""
    return {"underlying_indices": service.get_underlying_indices(params)}


@router.get("/markets/list")
def list_markets(service: ETFService = Depends(get_etf_service)):
    """List all distinct ETF markets."""
    return {"markets": service.get_markets()}
