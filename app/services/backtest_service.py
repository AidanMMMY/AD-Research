"""Backtest service for persistence and management."""

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models.etl import BacktestResult
from app.services.backtest_engine import run_backtest, run_walk_forward


class BacktestService:
    """Service for backtest operations."""

    def __init__(self, db: Session):
        self.db = db

    def run_backtest(
        self,
        strategy_id: int,
        etf_code: str,
        strategy_type: str,
        params: dict[str, Any],
        start_date: date,
        end_date: date,
        initial_capital: float = 100000.0,
        commission_rate: float = 0.001,
        slippage_rate: float = 0.001,
        position_size: float = 1.0,
        risk_free_rate: float = 0.02,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """Run a backtest and persist results.

        Args:
            strategy_id: Strategy config ID.
            etf_code: ETF code to backtest.
            strategy_type: Type of strategy.
            params: Strategy parameters.
            start_date: Backtest start date.
            end_date: Backtest end date.
            initial_capital: Starting capital.
            commission_rate: Per-trade commission rate (single side).
            slippage_rate: Per-trade slippage rate (single side).
            position_size: Position size ratio (0.0 - 1.0).
            risk_free_rate: Annual risk-free rate used in Sharpe calculation.

        Returns:
            Dict with backtest results and metadata.
        """
        # Run the backtest engine
        result = run_backtest(
            etf_code=etf_code,
            strategy_type=strategy_type,
            params=params,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            position_size=position_size,
            risk_free_rate=risk_free_rate,
            db=self.db,
        )

        # Persist to database
        backtest = BacktestResult(
            user_id=user_id,
            strategy_id=strategy_id,
            start_date=start_date,
            end_date=end_date,
            metrics=result.metrics,
            trades=[
                {
                    "entry_date": t.entry_date.isoformat(),
                    "exit_date": t.exit_date.isoformat() if t.exit_date else None,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "side": t.side,
                    "pnl": round(t.pnl, 2),
                    "pnl_pct": round(t.pnl_pct * 100, 2),
                }
                for t in result.trades
            ],
            config_snapshot={
                "etf_code": etf_code,
                "strategy_type": strategy_type,
                "params": params,
                "initial_capital": initial_capital,
                "commission_rate": commission_rate,
                "slippage_rate": slippage_rate,
                "position_size": position_size,
                "risk_free_rate": risk_free_rate,
            },
        )
        self.db.add(backtest)
        self.db.commit()
        self.db.refresh(backtest)

        return {
            "id": backtest.id,
            "strategy_id": strategy_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "metrics": result.metrics,
            "trades": result.trades,
            "daily_nav": result.daily_nav,
            "signals": result.signals,
            "created_at": backtest.created_at.isoformat() if backtest.created_at else None,
        }

    def get_backtests(self, strategy_id: int | None = None, limit: int = 50, user_id: int | None = None) -> list[dict[str, Any]]:
        """Get backtest results."""
        query = self.db.query(BacktestResult)
        if user_id:
            query = query.filter(BacktestResult.user_id == user_id)
        if strategy_id:
            query = query.filter(BacktestResult.strategy_id == strategy_id)
        results = query.order_by(BacktestResult.created_at.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "strategy_id": r.strategy_id,
                # etf_code is not a table column; it lives in config_snapshot.
                "etf_code": (r.config_snapshot or {}).get("etf_code"),
                "start_date": r.start_date.isoformat() if r.start_date else None,
                "end_date": r.end_date.isoformat() if r.end_date else None,
                "metrics": r.metrics,
                "trade_count": len(r.trades) if r.trades else 0,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in results
        ]

    def get_backtest(self, backtest_id: int, user_id: int | None = None) -> dict[str, Any] | None:
        """Get a single backtest by ID."""
        query = self.db.query(BacktestResult).filter(BacktestResult.id == backtest_id)
        if user_id:
            query = query.filter(BacktestResult.user_id == user_id)
        r = query.first()
        if not r:
            return None
        return {
            "id": r.id,
            "strategy_id": r.strategy_id,
            "start_date": r.start_date.isoformat() if r.start_date else None,
            "end_date": r.end_date.isoformat() if r.end_date else None,
            "metrics": r.metrics,
            "trades": r.trades,
            "daily_nav": [],  # Not persisted to save space
            "config_snapshot": r.config_snapshot,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }

    # ------------------------------------------------------------------
    # Walk-forward evaluation
    # ------------------------------------------------------------------

    def run_walk_forward(
        self,
        strategy_id: int,
        etf_code: str,
        strategy_type: str,
        params: dict[str, Any],
        start_date: date,
        end_date: date,
        train_pct: float = 0.6,
        n_folds: int = 3,
        initial_capital: float = 100000.0,
        commission_rate: float = 0.001,
        slippage_rate: float = 0.001,
        position_size: float = 1.0,
        risk_free_rate: float = 0.02,
        execution_price_model: str = "open",
        market: str = "cn_a",
        apply_friction: bool = True,
    ) -> dict[str, Any]:
        """Internal entry point for walk-forward evaluation.

        Forwards into ``app.services.backtest_engine.run_walk_forward``.
        No HTTP endpoint exists yet — this is wired up at the service
        layer so a future frontend / admin agent can plug it in without
        any engine-level changes.
        """
        cfg = {
            "etf_code": etf_code,
            "strategy_type": strategy_type,
            "params": params,
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": initial_capital,
            "commission_rate": commission_rate,
            "slippage_rate": slippage_rate,
            "position_size": position_size,
            "risk_free_rate": risk_free_rate,
            "execution_price_model": execution_price_model,
            "market": market,
            "apply_friction": apply_friction,
        }
        result = run_walk_forward(
            cfg,
            train_pct=train_pct,
            n_folds=n_folds,
            db=self.db,
        )
        # Stamp with the requesting strategy id for traceability.
        result["strategy_id"] = strategy_id
        return result
