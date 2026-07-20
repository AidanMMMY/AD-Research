"""Backtest Pydantic schemas."""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class BacktestCreate(BaseModel):
    """Create backtest request."""

    strategy_id: int
    etf_code: str
    start_date: date
    end_date: date
    initial_capital: float = 100000.0
    commission_rate: float = 0.001
    slippage_rate: float = 0.001
    position_size: float = 1.0
    risk_free_rate: float = 0.02


class BacktestMetrics(BaseModel):
    """Backtest performance metrics."""

    initial_capital: float
    final_nav: float
    total_return: float
    annualized_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    trade_count: int
    avg_win: float
    avg_loss: float
    trading_days: int
    commission_rate: float = 0.001
    slippage_rate: float = 0.001
    position_size: float = 1.0
    risk_free_rate: float = 0.02
    # New (quant P0-9) — None means "not computable" rather than 0
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    var_95: float | None = None
    cvar_95: float | None = None
    max_drawdown_duration: int | None = None
    annualization_factor: int = 252
    # Execution-config echoes
    execution_price_model: str = "open"
    market: str = "cn_a"
    apply_friction: bool = True


class BacktestTrade(BaseModel):
    """Backtest trade record."""

    entry_date: str
    exit_date: str | None = None
    entry_price: float
    exit_price: float
    side: str
    pnl: float
    pnl_pct: float


class BacktestResponse(BaseModel):
    """Backtest response."""

    id: int
    strategy_id: int
    start_date: str
    end_date: str
    metrics: dict[str, Any]
    trades: list[dict[str, Any]]
    daily_nav: list[dict[str, Any]]
    signals: list[dict[str, Any]]
    config_snapshot: dict[str, Any] | None = None
    created_at: str | None = None


class BacktestListItem(BaseModel):
    """Backtest list item."""

    id: int
    strategy_id: int
    etf_code: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    metrics: dict[str, Any]
    trade_count: int
    created_at: str | None = None


class BacktestListResponse(BaseModel):
    """Backtest list response."""

    items: list[BacktestListItem]


# ---------------------------------------------------------------------------
# Cross-sectional backtest schema (quant P1)
# ---------------------------------------------------------------------------


class CrossSectionalBacktestCreate(BacktestCreate):
    """Create cross-sectional (multi-symbol) backtest request.

    The legacy single-code path is preserved via the parent class.
    Provide ``etf_codes`` to switch into cross-sectional mode.
    """

    etf_codes: list[str] | None = None
    # Allocation per symbol is fixed at ``1 / len(etf_codes)`` (equal
    # weights, daily rebalance to the long side of signals). No
    # configurable field for that today.


# ---------------------------------------------------------------------------
# Parameter optimization schemas (quant P1)
# ---------------------------------------------------------------------------


class OptimizeRequest(BaseModel):
    """Request body for ``POST /backtests/optimize``.

    Accepts the same inputs as ``BacktestCreate`` plus a ``grid`` map
    specifying the value lists to sweep over. ``etf_code`` and
    ``etf_codes`` are both honoured — when ``etf_codes`` is provided
    the optimizer runs a cross-sectional sweep.
    """

    strategy_type: str = Field(..., description="Registered strategy identifier")
    etf_code: str | None = None
    etf_codes: list[str] | None = None
    base_params: dict[str, Any] = Field(default_factory=dict)
    grid: dict[str, list[Any]] = Field(
        default_factory=dict,
        description="Mapping of param_name -> [v1, v2, ...]",
    )
    start_date: date
    end_date: date
    initial_capital: float = 100000.0
    commission_rate: float = 0.001
    slippage_rate: float = 0.001
    position_size: float = 1.0
    risk_free_rate: float = 0.02
    execution_price_model: str = "open"
    market: str = "cn_a"
    apply_friction: bool = True
    top_n: int = Field(10, ge=1, le=100, description="Number of Pareto-optimal rows to return")


class OptimizeResponse(BaseModel):
    """Response body for ``POST /backtests/optimize``."""

    top_n: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Up to ``top_n`` Pareto-optimal candidates by Sharpe.",
    )
    full_sweep_size: int = 0
    strategy_type: str
    grid_keys: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Composite strategy schema (quant P1)
# ---------------------------------------------------------------------------


class CompositeComponent(BaseModel):
    """One component inside a composite strategy."""

    type: str = Field(..., description="Component strategy_type")
    params: dict[str, Any] = Field(default_factory=dict)
    weight: float = 1.0


class CompositeStrategyConfig(BaseModel):
    """Composite strategy configuration.

    Used as the body of ``POST /backtests/composite``. The endpoint
    routes the request through the generic ``CompositeStrategy`` in
    ``app.strategies.base`` — register your components by their
    ``strategy_type`` strings.
    """

    components: list[CompositeComponent] = Field(..., min_length=1)
    aggregation: str = Field(
        "weighted",
        description="weighted | vote | unanimous",
        pattern="^(weighted|vote|unanimous)$",
    )
    holding_period: int = 20

    def as_params(self) -> dict[str, Any]:
        """Render into the dict accepted by ``run_backtest``/``Strategy``."""
        return {
            "components": [
                {"type": c.type, "params": c.params, "weight": c.weight}
                for c in self.components
            ],
            "aggregation": self.aggregation,
            "holding_period": self.holding_period,
        }


class CompositeBacktestRequest(CompositeStrategyConfig):
    """Composite backtest request: composite config + backtest envelope."""

    etf_code: str = Field(..., description="Single-instrument target")
    start_date: date
    end_date: date
    initial_capital: float = 100000.0
    commission_rate: float = 0.001
    slippage_rate: float = 0.001
    position_size: float = 1.0
    risk_free_rate: float = 0.02
    execution_price_model: str = "open"
    market: str = "cn_a"
    apply_friction: bool = True
