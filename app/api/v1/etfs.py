"""ETF API routes.

Provides endpoints for listing, filtering, and retrieving ETF basic information.
"""

from datetime import date as _date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_etf_service
from app.models.etf import ETFInfo, InstrumentDailyBar
from app.schemas.etf import (
    ETFFilterParams,
    ETFHoldingDiffResponse,
    ETFHoldingResponse,
    ETFHoldingSnapshotListResponse,
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
    listing_market: str = Query(None, description="Filter by listing market (上海/深圳/北京)"),
    board: str = Query(None, description="Filter by A-share board (主板/创业板/科创板/北交所)"),
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
        listing_market=listing_market,
        board=board,
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


@router.get("/{code}/holdings", response_model=ETFHoldingResponse)
def get_etf_holdings(
    code: str,
    date: _date | None = Query(
        None,
        description=(
            "Reporting-period date (YYYY-MM-DD). When omitted, returns the "
            "latest snapshot across all available dates."
        ),
    ),
    service: ETFService = Depends(get_etf_service),
):
    """Return holdings for an ETF, optionally scoped to a single reporting period.

    With no ``date`` param: returns the latest top-N holdings (existing
    behaviour, backwards-compatible).

    With ``date=YYYY-MM-DD``: returns the holdings snapshot whose
    ``holdings_as_of_date`` equals the requested date. The endpoint
    returns 404 when the ETF has no holdings on that date so the
    frontend can fall back to the snapshot-list endpoint.
    """
    if not service.get_etf(code):
        raise HTTPException(status_code=404, detail=f"ETF {code} not found")
    if date is None:
        return service.get_holdings(code)
    result = service.get_holdings_by_date(code, date)
    if not result["holdings"]:
        raise HTTPException(
            status_code=404,
            detail=f"ETF {code} has no holdings snapshot for {date.isoformat()}",
        )
    return result


@router.get(
    "/{code}/holdings/snapshots",
    response_model=ETFHoldingSnapshotListResponse,
)
def list_etf_holdings_snapshots(
    code: str,
    service: ETFService = Depends(get_etf_service),
):
    """List the available quarterly reporting-period snapshots for an ETF.

    Returns one entry per distinct ``holdings_as_of_date`` with the
    holding count and total weight for that period. Newest first so
    the frontend can render a reverse-chronological timeline without
    re-sorting client-side.
    """
    if not service.get_etf(code):
        raise HTTPException(status_code=404, detail=f"ETF {code} not found")
    return {"items": service.list_holdings_snapshots(code)}


@router.get(
    "/{code}/holdings/diff",
    response_model=ETFHoldingDiffResponse,
)
def diff_etf_holdings(
    code: str,
    from_: _date = Query(..., alias="from", description="Earlier reporting date (YYYY-MM-DD)"),
    to: _date = Query(..., description="Later reporting date (YYYY-MM-DD)"),
    service: ETFService = Depends(get_etf_service),
):
    """Diff two reporting-period snapshots for an ETF.

    Returns per-holding weight + share deltas, status (added /
    removed / increased / decreased / unchanged), and aggregate
    counters. ``from`` is the earlier date and ``to`` is the later
    date; the result is meaningless if the dates are swapped, but
    the endpoint does not enforce ordering so the caller stays in
    control.
    """
    if not service.get_etf(code):
        raise HTTPException(status_code=404, detail=f"ETF {code} not found")
    return service.diff_holdings(code, from_, to)


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


@router.get("/listing-markets/list")
def list_listing_markets(
    params: ETFFilterParams = Depends(parse_etf_filter_params),
    service: ETFService = Depends(get_etf_service),
):
    """List distinct A-share listing markets (上海/深圳/北京)."""
    return {"listing_markets": service.get_listing_markets(params)}


@router.get("/boards/list")
def list_boards(
    params: ETFFilterParams = Depends(parse_etf_filter_params),
    service: ETFService = Depends(get_etf_service),
):
    """List distinct A-share boards (主板/创业板/科创板/北交所)."""
    return {"boards": service.get_boards(params)}
