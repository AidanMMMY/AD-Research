"""Futures API routes.

Exposes:
  GET /futures/contracts   — paginated contract list, filterable by exchange/product
  GET /futures/daily       — historical daily bars for a contract
  GET /futures/dashboard   — latest-day data grouped by product category
  GET /futures/leaderboard — gainers / losers on the latest trade date
  GET /futures/stats       — diagnostics counts
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.core.database import SessionLocal
from app.core.redis_client import redis_lock
from app.data.pipelines.futures import (
    FuturesContractDiscoveryPipeline,
    FuturesDailyPipeline,
)
from app.schemas.auth import UserResponse
from app.schemas.futures import (
    FuturesContractListResponse,
    FuturesContractOut,
    FuturesDailyBarListResponse,
    FuturesDailyBarOut,
    FuturesDashboardResponse,
    FuturesFilterParams,
    FuturesLeaderboardResponse,
)
from app.services.futures_service import FuturesService

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


def _get_service(db: Session) -> FuturesService:
    return FuturesService(db)


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


@router.get("/stats")
def futures_stats(db: Session = Depends(get_db)):
    """Diagnostics counts for /etl-status dashboards."""
    return _get_service(db).stats()


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------


@router.get("/contracts", response_model=FuturesContractListResponse)
def list_futures_contracts(
    exchange: str | None = Query(None, description="SHFE/DCE/CZCE/CFFEX/INE/GFEX"),
    product: str | None = Query(
        None, description="金属/能源化工/农产品/金融期货"
    ),
    is_main: bool = Query(True, description="Filter to main continuous contracts"),
    search: str | None = Query(None, description="Search by code or name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """List known futures main contracts."""
    params = FuturesFilterParams(
        exchange=exchange,
        product=product,
        is_main=is_main,
        search=search,
        page=page,
        page_size=page_size,
    )
    service = _get_service(db)
    items, total = service.list_contracts(params)
    return FuturesContractListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# Daily bars
# ---------------------------------------------------------------------------


@router.get("/daily", response_model=FuturesDailyBarListResponse)
def get_futures_daily(
    code: str | None = Query(None, description="Main contract code, e.g. CU0"),
    start_date: date | None = Query(None, alias="start_date"),
    end_date: date | None = Query(None, alias="end_date"),
    limit: int = Query(365, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    """Historical daily OHLCV bars for a futures contract."""
    service = _get_service(db)
    bars = service.get_daily_bars(
        code=code, start=start_date, end=end_date, limit=limit
    )
    # Returned bars are sorted desc (newest first); reverse for natural time order
    bars = list(reversed(bars))
    return FuturesDailyBarListResponse(
        items=[FuturesDailyBarOut.model_validate(_bar_out_dict(b, code)) for b in bars],
        count=len(bars),
        code=code,
    )


def _bar_out_dict(bar, code: str) -> dict:
    """Build a plain dict that fits FuturesDailyBarOut.model_validate."""
    settle_change = None
    if bar.settle is not None and bar.pre_settle not in (None, 0):
        try:
            settle_change = (
                (float(bar.settle) - float(bar.pre_settle))
                / float(bar.pre_settle)
            ) * 100.0
        except Exception:
            settle_change = None
    return {
        "code": code or bar.code,
        "trade_date": bar.trade_date,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "settle": bar.settle,
        "pre_settle": bar.pre_settle,
        "volume": bar.volume,
        "open_interest": bar.open_interest,
        "turnover": bar.turnover,
        "warehouse_receipts": bar.warehouse_receipts,
        "settle_change_pct": settle_change,
        "change_pct": None,
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("/dashboard", response_model=FuturesDashboardResponse)
def get_futures_dashboard(db: Session = Depends(get_db)):
    """Latest-day data grouped by product category for the home page."""
    return _get_service(db).build_dashboard()


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------


@router.get("/leaderboard", response_model=FuturesLeaderboardResponse)
def get_futures_leaderboard(
    exchange: str | None = Query(None, description="Filter by exchange code"),
    direction: str = Query("gainers", description="gainers / losers"),
    top: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Top N contracts by settle_change_pct on the latest trade date."""
    if direction not in ("gainers", "losers"):
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="direction must be 'gainers' or 'losers'")
    return _get_service(db).build_leaderboard(
        exchange=exchange, direction=direction, top_n=top
    )


# ---------------------------------------------------------------------------
# Manual refresh
# ---------------------------------------------------------------------------


@router.post("/refresh", status_code=202)
def refresh_futures(
    _admin: UserResponse = Depends(require_admin),
    include_discovery: bool = Query(True, description="Also refresh main contract list"),
) -> dict[str, str]:
    """Manually trigger a refresh of futures contracts and daily bars (admin only).

    By default this runs contract discovery first, then daily bars. If the
    contract list is already populated, set ``include_discovery=false`` to
    fetch only the latest daily bars.
    """
    with redis_lock("futures_refresh", expire_seconds=1800) as acquired:
        if not acquired:
            from fastapi import HTTPException

            raise HTTPException(status_code=409, detail="Futures refresh already in progress")

        db = SessionLocal()
        try:
            if include_discovery:
                discovery = FuturesContractDiscoveryPipeline(db)
                discovery_result = discovery.run_with_retry(max_attempts=1)
                if not discovery_result.success:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Futures contract discovery failed: {discovery_result.error}",
                    )

            daily = FuturesDailyPipeline(db)
            daily_result = daily.run_with_retry(max_attempts=1)
            if not daily_result.success:
                raise HTTPException(
                    status_code=500,
                    detail=f"Futures daily refresh failed: {daily_result.error}",
                )

            return {
                "status": "ok",
                "contracts": str(discovery_result.records if include_discovery else 0),
                "daily_bars": str(daily_result.records),
            }
        finally:
            db.close()
