"""Strategy configuration service.

Provides CRUD for strategy configs and preset strategy templates.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.models.etl import StrategyConfig

# Preset strategy templates
STRATEGY_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "动量策略",
        "description": "基于价格动量的趋势跟踪策略",
        "strategy_type": "momentum",
        "params": {
            "momentum_window": {"label": "动量窗口", "type": "int", "default": 20, "min": 5, "max": 252},
            "threshold": {"label": "动量阈值", "type": "float", "default": 0.05, "min": 0.01, "max": 0.5},
            "holding_period": {"label": "持有周期", "type": "int", "default": 20, "min": 5, "max": 60},
        },
    },
    {
        "name": "均值回归",
        "description": "基于价格偏离均值的反转策略",
        "strategy_type": "mean_reversion",
        "params": {
            "lookback_window": {"label": "回望窗口", "type": "int", "default": 20, "min": 5, "max": 60},
            "z_score_threshold": {"label": "Z-Score阈值", "type": "float", "default": 2.0, "min": 1.0, "max": 4.0},
            "holding_period": {"label": "持有周期", "type": "int", "default": 5, "min": 1, "max": 20},
        },
    },
    {
        "name": "RSI策略",
        "description": "基于RSI超买超卖的动量策略",
        "strategy_type": "rsi",
        "params": {
            "rsi_period": {"label": "RSI周期", "type": "int", "default": 14, "min": 5, "max": 30},
            "overbought": {"label": "超买阈值", "type": "int", "default": 70, "min": 60, "max": 90},
            "oversold": {"label": "超卖阈值", "type": "int", "default": 30, "min": 10, "max": 40},
            "holding_period": {"label": "持有周期", "type": "int", "default": 5, "min": 1, "max": 20},
        },
    },
]


class StrategyService:
    """Service for strategy configuration management."""

    def __init__(self, db: Session):
        self.db = db

    def get_templates(self) -> list[dict[str, Any]]:
        """Get all preset strategy templates."""
        return STRATEGY_TEMPLATES

    def get_strategies(self) -> list[dict[str, Any]]:
        """Get all user-created strategies."""
        strategies = self.db.query(StrategyConfig).all()
        return [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "strategy_type": s.strategy_type,
                "params": s.params,
                "is_active": s.is_active,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in strategies
        ]

    def get_strategy(self, strategy_id: int) -> dict[str, Any] | None:
        """Get a single strategy by ID."""
        s = self.db.query(StrategyConfig).filter(StrategyConfig.id == strategy_id).first()
        if not s:
            return None
        return {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "strategy_type": s.strategy_type,
            "params": s.params,
            "is_active": s.is_active,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }

    def create_strategy(
        self,
        name: str,
        description: str,
        strategy_type: str,
        params: dict[str, Any],
        is_active: bool = True,
    ) -> dict[str, Any]:
        """Create a new strategy configuration."""
        strategy = StrategyConfig(
            name=name,
            description=description,
            strategy_type=strategy_type,
            params=params,
            is_active=is_active,
        )
        self.db.add(strategy)
        self.db.commit()
        self.db.refresh(strategy)
        return self.get_strategy(strategy.id)

    def update_strategy(self, strategy_id: int, **kwargs) -> dict[str, Any] | None:
        """Update a strategy configuration."""
        strategy = self.db.query(StrategyConfig).filter(StrategyConfig.id == strategy_id).first()
        if not strategy:
            return None
        for key, value in kwargs.items():
            if hasattr(strategy, key):
                setattr(strategy, key, value)
        self.db.commit()
        self.db.refresh(strategy)
        return self.get_strategy(strategy.id)

    def delete_strategy(self, strategy_id: int) -> bool:
        """Delete a strategy configuration."""
        strategy = self.db.query(StrategyConfig).filter(StrategyConfig.id == strategy_id).first()
        if not strategy:
            return False
        self.db.delete(strategy)
        self.db.commit()
        return True
