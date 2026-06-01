"""Signal API routes."""

from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_signal_service, get_strategy_service
from app.schemas.signal import (
    SignalGenerateRequest,
    SignalGenerateResponse,
    SignalListResponse,
)
from app.services.signal_service import SignalService
from app.services.strategy_service import StrategyService

router = APIRouter()


@router.get("", response_model=SignalListResponse)
def list_signals(
    strategy_id: Optional[int] = None,
    etf_code: Optional[str] = None,
    trade_date: Optional[date] = None,
    limit: int = 100,
    service: SignalService = Depends(get_signal_service),
):
    """Get signals with optional filtering."""
    items = service.get_signals(
        strategy_id=strategy_id,
        etf_code=etf_code,
        trade_date=trade_date,
        limit=limit,
    )
    return SignalListResponse(items=items)


@router.get("/latest", response_model=SignalListResponse)
def get_latest_signals(
    limit: int = 50,
    service: SignalService = Depends(get_signal_service),
):
    """Get the latest signals."""
    items = service.get_latest_signals(limit=limit)
    return SignalListResponse(items=items)


@router.post("/generate", response_model=SignalGenerateResponse)
def generate_signals(
    data: SignalGenerateRequest,
    signal_service: SignalService = Depends(get_signal_service),
    strategy_service: StrategyService = Depends(get_strategy_service),
):
    """Manually trigger signal generation."""
    strategy = strategy_service.get_strategy(data.strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    trade_date = data.trade_date or date.today()
    signals = signal_service.generate_signals(
        strategy_id=data.strategy_id,
        etf_code=data.etf_code,
        strategy_type=strategy["strategy_type"],
        params=strategy["params"],
        trade_date=trade_date,
    )
    return SignalGenerateResponse(signals=signals)
