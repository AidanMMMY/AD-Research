"""Macro-indicator API routes.

Read endpoints surface the ``macro_indicator`` table (currently
populated by FRED; akshare/NBS/PBOC integrations planned).  A single
admin-only POST endpoint triggers a manual FRED refresh for ops/QA.

Phase 2 adds the China-specific surface backed by akshare:

* ``GET /api/v1/macro/indicators`` — paginated, filtered list of
  observations (FRED + akshare).
* ``GET /api/v1/macro/latest`` — latest snapshot per ``code+region``.
* ``GET /api/v1/macro/codes`` — distinct codes for filter dropdowns.
* ``POST /api/v1/macro/refresh-china`` — manual akshare refresh.
"""

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user, require_admin
from app.core.database import SessionLocal
from app.core.redis_client import redis_lock
from app.schemas.auth import UserResponse
from app.schemas.macro import (
    MacroCodeListResponse,
    MacroIndicatorLatestItem,
    MacroIndicatorListResponse,
    MacroIndicatorSeries,
    MacroLatestResponse,
    MacroRefreshResponse,
)
from app.services.macro.fred_service import FredService
from app.services.macro_service import MacroDataService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/macro",
    tags=["Macro Indicators"],
    dependencies=[Depends(get_current_user)],
)


def _get_service():
    """Yield a FredService bound to a short-lived session."""
    db = SessionLocal()
    try:
        yield FredService(db=db)
    finally:
        db.close()


def _macro_service() -> MacroDataService:
    """Yield a ``MacroDataService`` bound to a short-lived session."""
    db = SessionLocal()
    try:
        yield MacroDataService(db)
    finally:
        db.close()


@router.get("/indicators", response_model=list[MacroIndicatorLatestItem])
def list_indicators(
    region: str | None = Query(None, description="Filter by region code (e.g. 'us')"),
    service: FredService = Depends(_get_service),
    macro_service: MacroDataService = Depends(_macro_service),
) -> list[MacroIndicatorLatestItem]:
    """List all registered macro indicators with their latest value.

    US data is backed by FredService; China data is backed by
    MacroDataService so the China macro dashboard can surface the
    akshare/NBS/PBOC indicators.
    """
    if region == "cn":
        snapshot = macro_service.latest_snapshot(region="cn")
        return [MacroIndicatorLatestItem(**item) for item in snapshot["items"]]
    items = service.list_indicators(region=region)
    return [MacroIndicatorLatestItem(**item) for item in items]


@router.get("/indicators/{code}", response_model=MacroIndicatorSeries)
def get_indicator_series(
    code: str,
    start_date: date | None = Query(None, description="ISO date inclusive"),
    end_date: date | None = Query(None, description="ISO date inclusive"),
    limit: int = Query(500, ge=1, le=5000),
    service: FredService = Depends(_get_service),
    macro_service: MacroDataService = Depends(_macro_service),
) -> MacroIndicatorSeries:
    """Return the time-series for a single indicator (oldest → newest).

    Falls back to ``MacroDataService.get_series`` (pure DB lookup) if
    the code is not in the static FRED registry.  This is how the
    ``global_*`` codes upserted by the yfinance/akshare
    global-indices job get a chart endpoint without being added to
    the FRED registry.
    """
    series = service.get_series(
        code=code, start_date=start_date, end_date=end_date, limit=limit
    )
    if series is None:
        series = macro_service.get_series(
            code=code, start_date=start_date, end_date=end_date, limit=limit
        )
    if series is None:
        raise HTTPException(status_code=404, detail=f"Unknown indicator code: {code}")
    return MacroIndicatorSeries(**series)


@router.post(
    "/refresh",
    response_model=MacroRefreshResponse,
    dependencies=[Depends(require_admin)],
)
def trigger_fred_refresh(
    lookback_days: int = Query(180, ge=1, le=3650),
) -> MacroRefreshResponse:
    """Manually trigger a FRED refresh (admin only)."""
    db = SessionLocal()
    try:
        service = FredService(db=db)
        result = service.refresh(lookback_days=lookback_days)
        return MacroRefreshResponse(
            written=result.get("written", 0),
            series_count=result.get("series_count", 0),
            failed=result.get("failed", []),
            started_at=result["started_at"],
            finished_at=result["finished_at"],
        )
    except Exception as exc:
        logger.exception("Manual FRED refresh failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"FRED refresh failed: {exc}") from exc
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Phase 2 — China macro surface backed by akshare
# ---------------------------------------------------------------------------


@router.get("/indicators-list", response_model=MacroIndicatorListResponse)
def list_indicators_paginated(
    region: str | None = Query(None, description="Filter by region (cn/us/global)"),
    code: str | None = Query(None, description="Filter by indicator code"),
    start_period: date | None = Query(
        None, description="Inclusive period start (YYYY-MM-DD)"
    ),
    end_period: date | None = Query(
        None, description="Inclusive period end (YYYY-MM-DD)"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    service: MacroDataService = Depends(_macro_service),
) -> Any:
    """Return a paginated, filtered list of macro indicator observations.

    Combines every region/source — useful for charting a single
    indicator across its full history.
    """
    return service.list_indicators(
        region=region,
        code=code,
        start_period=start_period,
        end_period=end_period,
        page=page,
        page_size=page_size,
    )


@router.get("/latest", response_model=MacroLatestResponse)
def get_macro_latest(
    region: str | None = Query(None, description="Filter by region (cn/us/global)"),
    service: MacroDataService = Depends(_macro_service),
) -> Any:
    """Return the latest observation for every (code, region) pair."""
    return service.latest_snapshot(region=region)


@router.get("/codes", response_model=MacroCodeListResponse)
def get_macro_codes(
    region: str | None = Query(None, description="Filter by region (cn/us/global)"),
    service: MacroDataService = Depends(_macro_service),
) -> Any:
    """Return the distinct set of indicator codes for the filter UI."""
    return {"items": service.list_codes(region=region)}


@router.post("/refresh-china", status_code=202)
def refresh_china_macro(
    _user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    """Manually trigger a China macro refresh via akshare.

    Concurrent runs are blocked by a Redis lock so the scheduler
    and the manual-refresh button cannot pile up requests.
    """
    with redis_lock("macro_china_refresh", expire_seconds=1800) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=409,
                detail="China macro refresh already in progress",
            )
        from app.services.macro.scheduler import run_china_macro_refresh

        return run_china_macro_refresh()


# ---------------------------------------------------------------------------
# Phase 5d — Global market indices (yfinance + akshare)
# ---------------------------------------------------------------------------


@router.get("/indices/global")
def get_global_indices_realtime() -> dict[str, Any]:
    """Return the latest global index snapshot without going through the DB.

    Hits yfinance + akshare live so the Global Markets page can
    surface a near-realtime value before the 16:00 Asia/Shanghai
    scheduled upsert lands.  Each item is
    ``{code, name_zh, name_en, value, prev_close, change, change_pct, as_of, source}``.

    Best-effort: per-ticker failures are logged and skipped; the
    response always returns 200 even when some tickers fail.
    """
    try:
        from app.services.macro.global_indices_fetcher import (
            fetch_all_global_indices,
        )

        items = fetch_all_global_indices()
    except Exception as exc:  # noqa: BLE001 - defensive
        logger.exception("global indices realtime fetch crashed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Reduce to the latest observation per code (sorted by period desc).
    latest_by_code: dict[str, dict] = {}
    for obs in items:
        code = obs.get("code")
        period = obs.get("period")
        if not code or not period:
            continue
        existing = latest_by_code.get(code)
        if existing is None or period > existing.get("period", ""):
            latest_by_code[code] = obs

    out: list[dict[str, Any]] = []
    for obs in latest_by_code.values():
        value = obs.get("value")
        prev_close = obs.get("prev_close")
        change = None
        change_pct = None
        if value is not None and prev_close not in (None, 0):
            change = round(float(value) - float(prev_close), 4)
            change_pct = round((float(value) - float(prev_close)) / float(prev_close) * 100.0, 4)
        out.append({
            "code": obs.get("code"),
            "name_zh": obs.get("name_zh"),
            "name_en": obs.get("name_en"),
            "unit": obs.get("unit", "指数"),
            "value": value,
            "prev_close": prev_close,
            "change": change,
            "change_pct": change_pct,
            "as_of": obs.get("period"),
            "source": obs.get("source", "yfinance"),
        })
    out.sort(key=lambda x: x.get("code") or "")
    return {"items": out, "count": len(out)}


@router.post("/refresh-global-indices", status_code=202)
def refresh_global_indices(
    _user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    """Manually trigger the global indices refresh (yfinance + akshare).

    Concurrent runs are blocked by a Redis lock.
    """
    with redis_lock("global_indices_daily", expire_seconds=3600) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=409,
                detail="Global indices refresh already in progress",
            )
        from app.services.macro.global_indices_fetcher import (
            run_global_indices_refresh,
        )

        return run_global_indices_refresh()