"""SEC EDGAR filings API routes.

Exposes:
  - GET  ``/sec-filings``             paginated list with filters
  - GET  ``/sec-filings/coverage``    coverage stats for the dashboard
  - GET  ``/sec-filings/{id}``        detail (incl. extracted XBRL metrics)
  - GET  ``/sec-filings/by-accession/{accession_number}``  alt lookup
  - POST ``/sec-filings/{id}/extract-metrics``  admin-only XBRL extraction
  - POST ``/sec-filings/refresh``     admin-only full pipeline refresh
  - POST ``/sec-filings/sync/{ticker}`` admin-only single-ticker sync
"""

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user, get_db, require_admin
from app.core.database import SessionLocal
from app.core.redis_client import redis_lock
from app.data.pipelines.sec_edgar import SecEdgarPipeline
from app.schemas.auth import UserResponse
from app.schemas.sec_filing import (
    SecFilingCoverageResponse,
    SecFilingDetail,
    SecFilingListResponse,
)
from app.services.sec_filing_service import SecFilingService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/sec-filings",
    tags=["SEC Filings"],
    dependencies=[Depends(get_current_user)],
)


def _service(db=Depends(get_db)) -> SecFilingService:
    return SecFilingService(db)


@router.get("", response_model=SecFilingListResponse)
def list_sec_filings(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ticker: str | None = None,
    cik: str | None = None,
    form_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    q: str | None = None,
    sort_by: str = Query("filing_date"),
    sort_dir: str = Query("desc"),
    service: SecFilingService = Depends(_service),
) -> SecFilingListResponse:
    """Return a paginated list of SEC EDGAR filings."""
    return service.list_filings(
        page=page,
        page_size=page_size,
        ticker=ticker,
        cik=cik,
        form_type=form_type,
        start_date=start_date,
        end_date=end_date,
        q=q,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@router.get("/coverage", response_model=SecFilingCoverageResponse)
def get_sec_filing_coverage(
    service: SecFilingService = Depends(_service),
) -> SecFilingCoverageResponse:
    """Return coverage stats (total filings, distinct tickers, status counts)."""
    data = service.get_coverage()
    return SecFilingCoverageResponse(**data)


@router.get("/by-accession/{accession_number}", response_model=SecFilingDetail)
def get_sec_filing_by_accession(
    accession_number: str,
    service: SecFilingService = Depends(_service),
) -> SecFilingDetail:
    """Return one SEC filing by accession number."""
    detail = service.get_filing_by_accession(accession_number)
    if detail is None:
        raise HTTPException(status_code=404, detail="Filing not found")
    return detail


@router.get("/{filing_id}", response_model=SecFilingDetail)
def get_sec_filing(
    filing_id: int,
    service: SecFilingService = Depends(_service),
) -> SecFilingDetail:
    """Return one SEC filing by id (includes extracted XBRL metrics)."""
    detail = service.get_filing(filing_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Filing not found")
    return detail


@router.post("/{filing_id}/extract-metrics")
def extract_metrics_for_filing(
    filing_id: int,
    _admin: UserResponse = Depends(require_admin),
    service: SecFilingService = Depends(_service),
) -> dict[str, Any]:
    """Trigger XBRL extraction for one filing (admin only)."""
    detail = service.get_filing(filing_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Filing not found")
    ok = service.extract_metrics_for_filing(detail["accession_number"])
    return {"status": "ok" if ok else "failed", "filing_id": filing_id}


@router.post("/sync/{ticker}")
def sync_ticker(
    ticker: str,
    _admin: UserResponse = Depends(require_admin),
    service: SecFilingService = Depends(_service),
) -> dict[str, Any]:
    """Pull SEC submissions for ``ticker`` and upsert (admin only)."""
    with redis_lock("sec_edgar_ticker_sync", expire_seconds=300) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=409,
                detail="SEC ticker sync already in progress",
            )
        written = service.sync_filings_for_ticker(ticker)
    return {"status": "ok", "ticker": ticker.upper(), "written": written}


@router.post("/refresh", status_code=202)
def refresh_sec_filings(
    _admin: UserResponse = Depends(require_admin),
    batch_size: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    """Trigger a full SEC EDGAR refresh (admin only).

    Pulls submissions for ``batch_size`` tickers from the cached SEC
    directory and attempts XBRL extraction for any pending rows.
    """
    with redis_lock("sec_edgar_refresh", expire_seconds=3600) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=409,
                detail="SEC EDGAR refresh already in progress",
            )
        db = SessionLocal()
        try:
            pipeline = SecEdgarPipeline(db, batch_size=batch_size)
            result = pipeline.run_with_retry(max_attempts=1)
            if not result.success:
                raise HTTPException(
                    status_code=500,
                    detail=f"SEC refresh failed: {result.error}",
                )
            return {
                "status": "ok",
                "records": str(result.records),
                "warnings": result.warnings,
            }
        finally:
            db.close()