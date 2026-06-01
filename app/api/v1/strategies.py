"""Strategy configuration API routes."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_strategy_service
from app.schemas.strategy import (
    StrategyCreate,
    StrategyListResponse,
    StrategyResponse,
    StrategyTemplate,
    StrategyUpdate,
)
from app.services.strategy_service import StrategyService

router = APIRouter()


@router.get("/templates", response_model=List[StrategyTemplate])
def list_templates(
    service: StrategyService = Depends(get_strategy_service),
):
    """Get all preset strategy templates."""
    return service.get_templates()


@router.get("", response_model=StrategyListResponse)
def list_strategies(
    service: StrategyService = Depends(get_strategy_service),
):
    """Get all user-created strategies."""
    items = service.get_strategies()
    return StrategyListResponse(items=items)


@router.post("", response_model=StrategyResponse, status_code=201)
def create_strategy(
    data: StrategyCreate,
    service: StrategyService = Depends(get_strategy_service),
):
    """Create a new strategy."""
    return service.create_strategy(
        name=data.name,
        description=data.description or "",
        strategy_type=data.strategy_type,
        params=data.params,
        is_active=data.is_active,
    )


@router.get("/{strategy_id}", response_model=StrategyResponse)
def get_strategy(
    strategy_id: int,
    service: StrategyService = Depends(get_strategy_service),
):
    """Get a strategy by ID."""
    strategy = service.get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


@router.put("/{strategy_id}", response_model=StrategyResponse)
def update_strategy(
    strategy_id: int,
    data: StrategyUpdate,
    service: StrategyService = Depends(get_strategy_service),
):
    """Update a strategy."""
    update_data = data.model_dump(exclude_unset=True)
    strategy = service.update_strategy(strategy_id, **update_data)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


@router.delete("/{strategy_id}", status_code=204)
def delete_strategy(
    strategy_id: int,
    service: StrategyService = Depends(get_strategy_service),
):
    """Delete a strategy."""
    if not service.delete_strategy(strategy_id):
        raise HTTPException(status_code=404, detail="Strategy not found")
    return None
