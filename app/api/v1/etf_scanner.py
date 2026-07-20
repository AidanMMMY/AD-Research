"""ETF scanner API routes."""

from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import get_etf_scanner_service, require_admin
from app.schemas.auth import UserResponse
from app.services.etf_scanner_service import ETFScannerService

router = APIRouter()


@router.post("/scan", response_model=dict[str, Any])
def trigger_scan(
    service: ETFScannerService = Depends(get_etf_scanner_service),
    _: UserResponse = Depends(require_admin),
):
    """Manually trigger an ETF market scan (admin only — heavy full-market job)."""
    return service.scan_market()


@router.get("/scan/logs", response_model=list[dict[str, Any]])
def get_scan_logs(
    limit: int = 50,
    service: ETFScannerService = Depends(get_etf_scanner_service),
):
    """Get ETF scan history logs."""
    return service.get_scan_logs(limit=limit)
