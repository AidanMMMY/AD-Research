"""Strategy configuration API routes."""


from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, get_strategy_service
from app.schemas.strategy import (
    StrategyCatalogItem,
    StrategyCreate,
    StrategyListResponse,
    StrategyResponse,
    StrategyRunRequest,
    StrategyRunResponse,
    StrategyTemplate,
    StrategyUpdate,
)
from app.services.strategy_engine import run_strategy_on_universe
from app.services.strategy_service import StrategyService

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/catalog", response_model=list[StrategyCatalogItem])
def list_catalog(
    service: StrategyService = Depends(get_strategy_service),
):
    """Get all registered strategy templates with metadata."""
    return service.get_templates()


@router.get("/catalog/{family}", response_model=list[StrategyCatalogItem])
def list_catalog_by_family(
    family: str,
    service: StrategyService = Depends(get_strategy_service),
):
    """Get registered strategy templates filtered by family."""
    all_templates = service.get_templates()
    return [t for t in all_templates if t.get("family") == family]


@router.post("/run", response_model=StrategyRunResponse)
def run_strategy(
    data: StrategyRunRequest,
    service: StrategyService = Depends(get_strategy_service),
):
    """Run a strategy on demand for a single instrument or a universe."""
    from datetime import date

    trade_date = data.trade_date or date.today()
    signals = run_strategy_on_universe(
        db=service.db,
        etf_codes=data.etf_codes,
        strategy_type=data.strategy_type,
        params=data.params,
        trade_date=trade_date,
        lookback_days=data.lookback_days,
    )
    return StrategyRunResponse(
        signals=signals,
        strategy_type=data.strategy_type,
        trade_date=trade_date.isoformat(),
        instrument_count=len(data.etf_codes),
        signal_count=len(signals),
    )


@router.get("/templates", response_model=list[StrategyTemplate])
def list_templates(
    service: StrategyService = Depends(get_strategy_service),
):
    """Get all preset strategy templates (backward-compatible)."""
    return service.get_templates()


@router.get("", response_model=StrategyListResponse)
def list_strategies(
    current_user=Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
):
    """Get all user-created strategies."""
    items = service.get_strategies(user_id=current_user.id)
    return StrategyListResponse(items=items)


@router.post("", response_model=StrategyResponse, status_code=201)
def create_strategy(
    data: StrategyCreate,
    current_user=Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
):
    """Create a new strategy."""
    return service.create_strategy(
        name=data.name,
        description=data.description or "",
        strategy_type=data.strategy_type,
        params=data.params,
        is_active=data.is_active,
        user_id=current_user.id,
    )


@router.get("/{strategy_id}", response_model=StrategyResponse)
def get_strategy(
    strategy_id: int,
    current_user=Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
):
    """Get a strategy by ID."""
    strategy = service.get_strategy(strategy_id, user_id=current_user.id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


@router.put("/{strategy_id}", response_model=StrategyResponse)
def update_strategy(
    strategy_id: int,
    data: StrategyUpdate,
    current_user=Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
):
    """Update a strategy."""
    update_data = data.model_dump(exclude_unset=True)
    strategy = service.update_strategy(strategy_id, user_id=current_user.id, **update_data)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


@router.delete("/{strategy_id}", status_code=204)
def delete_strategy(
    strategy_id: int,
    current_user=Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
):
    """Delete a strategy."""
    if not service.delete_strategy(strategy_id, user_id=current_user.id):
        raise HTTPException(status_code=404, detail="Strategy not found")
    return None
