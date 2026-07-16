"""Backtest API routes."""


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_backtest_service, get_current_user, get_db, get_strategy_service
from app.schemas.backtest import (
    BacktestCreate,
    BacktestListResponse,
    BacktestResponse,
    CompositeBacktestRequest,
    CompositeStrategyConfig,
    CrossSectionalBacktestCreate,
    OptimizeRequest,
    OptimizeResponse,
)
from app.services.backtest_engine import run_backtest
from app.services.backtest_service import BacktestService
from app.services.optimization_engine import grid_search, pareto_top_n
from app.services.strategy_service import StrategyService
from app.strategies.base import StrategyRegistry

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.post("", response_model=BacktestResponse, status_code=201)
def create_backtest(
    data: BacktestCreate,
    current_user=Depends(get_current_user),
    backtest_service: BacktestService = Depends(get_backtest_service),
    strategy_service: StrategyService = Depends(get_strategy_service),
):
    """Run a new backtest."""
    strategy = strategy_service.get_strategy(data.strategy_id, user_id=current_user.id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    result = backtest_service.run_backtest(
        **data.model_dump(),
        strategy_type=strategy["strategy_type"],
        params=strategy["params"],
        user_id=current_user.id,
    )
    return result


@router.get("", response_model=BacktestListResponse)
def list_backtests(
    strategy_id: int | None = None,
    limit: int = 50,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """Get backtest results."""
    items = service.get_backtests(strategy_id=strategy_id, limit=limit, user_id=current_user.id)
    return BacktestListResponse(items=items)


@router.get("/{backtest_id}", response_model=BacktestResponse)
def get_backtest(
    backtest_id: int,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """Get a backtest by ID."""
    result = service.get_backtest(backtest_id, user_id=current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return result


# ---------------------------------------------------------------------------
# Cross-sectional backtest (quant P1)
# ---------------------------------------------------------------------------


@router.post("/cross_sectional", response_model=BacktestResponse, status_code=201)
def create_cross_sectional_backtest(
    data: CrossSectionalBacktestCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
    backtest_service: BacktestService = Depends(get_backtest_service),
    strategy_service: StrategyService = Depends(get_strategy_service),
):
    """Run a cross-sectional (multi-symbol) backtest.

    Accepts the same envelope as ``BacktestCreate`` plus ``etf_codes``.
    The strategy that ``strategy_id`` points at in the DB is the one
    that gets run on every symbol in the universe with equal-weight
    daily rebalance to the long side of the signals.
    """
    etf_codes = data.etf_codes or []
    if not etf_codes:
        raise HTTPException(
            status_code=422,
            detail="etf_codes must be a non-empty list for cross-sectional backtest",
        )

    strategy = strategy_service.get_strategy(data.strategy_id, user_id=current_user.id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    engine = run_backtest(
        etf_code=data.etf_code,
        strategy_type=strategy["strategy_type"],
        params=strategy["params"],
        start_date=data.start_date,
        end_date=data.end_date,
        initial_capital=data.initial_capital,
        commission_rate=data.commission_rate,
        slippage_rate=data.slippage_rate,
        position_size=data.position_size,
        risk_free_rate=data.risk_free_rate,
        db=db,
        execution_price_model="open",
        market="cn_a",
        apply_friction=True,
        etf_codes=etf_codes,
    )

    return _serialize_engine_result(
        engine=engine,
        strategy_id=data.strategy_id,
        start_date=data.start_date,
        end_date=data.end_date,
        extra_config={
            "etf_codes": etf_codes,
            "mode": "cross_sectional",
            "initial_capital": data.initial_capital,
        },
        per_symbol=getattr(engine, "per_symbol", None),
    )


def _serialize_engine_result(
    *,
    engine,
    strategy_id: int,
    start_date,
    end_date,
    extra_config: dict | None = None,
    per_symbol: list | None = None,
) -> dict:
    """Convert a BacktestResult into the dict shape of BacktestResponse."""
    trades = []
    for t in (engine.trades or []):
        trades.append({
            "entry_date": t.entry_date.isoformat() if hasattr(t.entry_date, "isoformat") else str(t.entry_date),
            "exit_date": (
                t.exit_date.isoformat()
                if getattr(t, "exit_date", None) and hasattr(t.exit_date, "isoformat")
                else (str(t.exit_date) if t.exit_date else None)
            ),
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "side": t.side,
            "pnl": t.pnl,
            "pnl_pct": t.pnl_pct,
        })

    config_snapshot = dict(extra_config or {})
    if per_symbol is not None:
        config_snapshot["per_symbol"] = per_symbol

    return {
        "id": 0,
        "strategy_id": strategy_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "metrics": engine.metrics,
        "trades": trades,
        "daily_nav": list(engine.daily_nav or []),
        "signals": list(engine.signals or []),
        "config_snapshot": config_snapshot,
    }


# ---------------------------------------------------------------------------
# Parameter optimization (quant P1)
# ---------------------------------------------------------------------------


@router.post("/optimize", response_model=OptimizeResponse, status_code=200)
def create_optimize(
    data: OptimizeRequest,
    db: Session = Depends(get_db),
):
    """Run a grid search and return the Pareto-optimal candidate set.

    The cartesian product of ``grid`` is run end-to-end, then the top
    ``top_n`` candidates sorted by Sharpe ratio (with ``total_return``
    as tie-breaker) are returned. Failure candidates are surfaced
    inside the full sweep but never make the top-N cut.

    This endpoint intentionally does **not** persist results — it is
    designed for admin/research notebooks to ask "what were the best
    param combinations for this strategy on this window?" quickly.
    """
    if StrategyRegistry.get(data.strategy_type) is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown strategy_type: {data.strategy_type!r}",
        )

    sweep = grid_search(
        strategy_type=data.strategy_type,
        base_params=data.base_params,
        grid=data.grid,
        start_date=data.start_date,
        end_date=data.end_date,
        etf_code=data.etf_code,
        etf_codes=data.etf_codes,
        initial_capital=data.initial_capital,
        commission_rate=data.commission_rate,
        slippage_rate=data.slippage_rate,
        position_size=data.position_size,
        risk_free_rate=data.risk_free_rate,
        db=db,
        execution_price_model=data.execution_price_model,
        market=data.market,
        apply_friction=data.apply_friction,
    )
    top = pareto_top_n(sweep, n=data.top_n)

    return OptimizeResponse(
        top_n=top,
        full_sweep_size=len(sweep),
        strategy_type=data.strategy_type,
        grid_keys=list(data.grid.keys()),
    )


# ---------------------------------------------------------------------------
# Composite strategy (quant P1)
# ---------------------------------------------------------------------------


@router.post("/composite", response_model=BacktestResponse, status_code=201)
def create_composite_backtest(
    data: CompositeBacktestRequest,
    db: Session = Depends(get_db),
):
    """Run a backtest driven by a generic composite strategy.

    The composite config is rendered into ``CompositeStrategy`` params
    and forwarded to ``run_backtest``. All component strategies must
    already be registered (the registry's ``list_all`` is the source
    of truth).
    """
    config: CompositeStrategyConfig = data  # type: ignore[assignment]
    params = config.as_params()

    # Sanity-check all component strategies exist BEFORE running so the
    # caller gets a 422 instead of a 500 from deep in the engine.
    unknown = [
        comp.type
        for comp in config.components
        if StrategyRegistry.get(comp.type) is None
    ]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={"unknown_components": unknown},
        )

    result = run_backtest(
        etf_code=data.etf_code,
        strategy_type="composite",
        params=params,
        start_date=data.start_date,
        end_date=data.end_date,
        initial_capital=data.initial_capital,
        commission_rate=data.commission_rate,
        slippage_rate=data.slippage_rate,
        position_size=data.position_size,
        risk_free_rate=data.risk_free_rate,
        db=db,
        execution_price_model=data.execution_price_model,
        market=data.market,
        apply_friction=data.apply_friction,
    )

    return _serialize_engine_result(
        engine=result,
        strategy_id=0,
        start_date=data.start_date,
        end_date=data.end_date,
        extra_config={
            "mode": "composite",
            "composite_params": params,
        },
    )
