"""Backtest Pydantic schemas."""

from datetime import date
from typing import Any

from pydantic import BaseModel


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
    start_date: str | None = None
    end_date: str | None = None
    metrics: dict[str, Any]
    trade_count: int
    created_at: str | None = None


class BacktestListResponse(BaseModel):
    """Backtest list response."""

    items: list[BacktestListItem]
