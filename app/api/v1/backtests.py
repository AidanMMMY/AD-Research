"""Backtest API routes."""

from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_backtest_service, get_strategy_service
from app.schemas.backtest import (
    BacktestCreate,
    BacktestListResponse,
    BacktestResponse,
)
from app.services.backtest_service import BacktestService
from app.services.strategy_service import StrategyService

router = APIRouter()


@router.post("", response_model=BacktestResponse, status_code=201)
def create_backtest(
    data: BacktestCreate,
    backtest_service: BacktestService = Depends(get_backtest_service),
    strategy_service: StrategyService = Depends(get_strategy_service),
):
    """Run a new backtest."""
    strategy = strategy_service.get_strategy(data.strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    result = backtest_service.run_backtest(
        strategy_id=data.strategy_id,
        etf_code=data.etf_code,
        strategy_type=strategy["strategy_type"],
        params=strategy["params"],
        start_date=data.start_date,
        end_date=data.end_date,
        initial_capital=data.initial_capital,
    )
    return result


@router.get("", response_model=BacktestListResponse)
def list_backtests(
    strategy_id: Optional[int] = None,
    limit: int = 50,
    service: BacktestService = Depends(get_backtest_service),
):
    """Get backtest results."""
    items = service.get_backtests(strategy_id=strategy_id, limit=limit)
    return BacktestListResponse(items=items)


@router.get("/{backtest_id}", response_model=BacktestResponse)
def get_backtest(
    backtest_id: int,
    service: BacktestService = Depends(get_backtest_service),
):
    """Get a backtest by ID."""
    result = service.get_backtest(backtest_id)
    if not result:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return result
