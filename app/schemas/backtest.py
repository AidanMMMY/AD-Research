"""Backtest Pydantic schemas."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class BacktestCreate(BaseModel):
    """Create backtest request."""

    strategy_id: int
    etf_code: str
    start_date: date
    end_date: date
    initial_capital: float = 100000.0


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


class BacktestTrade(BaseModel):
    """Backtest trade record."""

    entry_date: str
    exit_date: Optional[str] = None
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
    metrics: Dict[str, Any]
    trades: List[Dict[str, Any]]
    daily_nav: List[Dict[str, Any]]
    signals: List[Dict[str, Any]]
    created_at: Optional[str] = None


class BacktestListItem(BaseModel):
    """Backtest list item."""

    id: int
    strategy_id: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    metrics: Dict[str, Any]
    trade_count: int
    created_at: Optional[str] = None


class BacktestListResponse(BaseModel):
    """Backtest list response."""

    items: List[BacktestListItem]
