"""ETF top-10 holdings — coverage / stats / blacklist endpoints.

Four read-only endpoints that power the operations dashboard's "ETF
持仓覆盖率" card and the post-ETL alert logic in
``app.scheduler_jobs.etf_holdings_quarterly``:

* ``GET /etf-holdings/stats``             — per-snapshot aggregates.
* ``GET /etf-holdings/coverage/latest``   — most recent snapshot only.
* ``GET /etf-holdings/coverage/{date}``   — coverage for a specific
                                            reporting period.
* ``GET /etf-holdings/unavailable``       — the 33-ETF structural
                                            blacklist.

All endpoints read the same shared ``etf_holding_stats`` view
(``b5e2c8f4a1d3`` migration) so the numbers stay consistent across
the dashboard, the alert log, and any downstream consumer.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.schemas.auth import UserResponse
from app.services.etf_holdings_coverage import (
    get_coverage_for,
    get_latest_coverage,
    list_snapshot_stats,
    list_unavailable,
)

router = APIRouter(
    prefix="/etf-holdings",
    tags=["ETF Holdings"],
    dependencies=[Depends(get_current_user)],
)


def _parse_date(raw: str) -> date:
    """Parse ``YYYY-MM-DD`` and reject anything else with a 422-friendly error."""
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date '{raw}', expected YYYY-MM-DD",
        ) from exc


@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    _user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    """Per-snapshot stats, newest first.

    Response shape::

        {
          "snapshots": [
            {
              "snapshot_date": "2025-12-31",
              "etf_count": 412,
              "row_count": 4102,
              "source_count": 2,
              "sources": ["tushare", "akshare"],
              "days_ago": 190,
              "eligible_etf_count": 510,
              "coverage_pct": 80.78,
              "coverage_alerts": []
            },
            ...
          ],
          "unavailable_count": 33,
          "generated_at": "2026-07-08T10:00:00+00:00"
        }
    """
    rows = list_snapshot_stats(db)
    unavailable = list_unavailable(db)
    return {
        "snapshots": [r.to_dict() for r in rows],
        "unavailable_count": len(unavailable),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


@router.get("/coverage/latest")
def get_coverage_latest(
    db: Session = Depends(get_db),
    _user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the most recent snapshot's coverage summary.

    Useful as a single-shot for the dashboard card without paginating
    the full ``/stats`` payload.  Returns ``{"coverage": null}`` when
    no snapshot exists (ETL never ran yet).
    """
    latest = get_latest_coverage(db)
    return {"coverage": latest.to_dict() if latest else None}


@router.get("/coverage/{snapshot_date}")
def get_coverage_for_date(
    snapshot_date: str = Path(
        ...,
        description="Reporting period date (YYYY-MM-DD)",
    ),
    db: Session = Depends(get_db),
    _user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the coverage for an explicit reporting period.

    Returns 404 when the requested date has no rows in ``etf_holding``
    — typically because the ETL has not run for that quarter yet.
    """
    target = _parse_date(snapshot_date)
    coverage = get_coverage_for(db, target)
    if coverage is None:
        raise HTTPException(
            status_code=404,
            detail=f"No holdings snapshot for {snapshot_date}",
        )
    return {"coverage": coverage.to_dict()}


@router.get("/unavailable")
def get_unavailable(
    db: Session = Depends(get_db),
    _user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the structurally-unavailable blacklist.

    Currently 33 A-share currency and physical-gold / SGE-gold ETFs
    (see the ``b5e2c8f4a1d3`` migration for the seeded list).  The
    endpoint is intentionally a plain list (no pagination) because
    the list is curated and will not exceed a few hundred rows.
    """
    items = list_unavailable(db)
    return {
        "items": items,
        "count": len(items),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
