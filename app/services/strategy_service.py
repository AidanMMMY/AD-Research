"""Strategy configuration service.

Provides CRUD for strategy configs and preset strategy templates.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.models.etl import StrategyConfig
from app.strategies.base import StrategyRegistry


class StrategyService:
    """Service for strategy configuration management."""

    def __init__(self, db: Session):
        self.db = db

    def get_templates(self) -> list[dict[str, Any]]:
        """Get all preset strategy templates from the registry."""
        return StrategyRegistry.list_all()

    def get_strategies(self, user_id: int) -> list[dict[str, Any]]:
        """Get all user-created strategies."""
        strategies = self.db.query(StrategyConfig).filter(StrategyConfig.user_id == user_id).all()
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

    def get_strategy(self, strategy_id: int, user_id: int) -> dict[str, Any] | None:
        """Get a single strategy by ID."""
        s = self.db.query(StrategyConfig).filter(
            StrategyConfig.id == strategy_id,
            StrategyConfig.user_id == user_id,
        ).first()
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
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """Create a new strategy configuration."""
        strategy = StrategyConfig(
            user_id=user_id,
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

    def update_strategy(self, strategy_id: int, user_id: int, **kwargs) -> dict[str, Any] | None:
        """Update a strategy configuration."""
        strategy = self.db.query(StrategyConfig).filter(
            StrategyConfig.id == strategy_id,
            StrategyConfig.user_id == user_id,
        ).first()
        if not strategy:
            return None
        for key, value in kwargs.items():
            if hasattr(strategy, key):
                setattr(strategy, key, value)
        self.db.commit()
        self.db.refresh(strategy)
        return self.get_strategy(strategy.id)

    def delete_strategy(self, strategy_id: int, user_id: int) -> bool:
        """Delete a strategy configuration."""
        strategy = self.db.query(StrategyConfig).filter(
            StrategyConfig.id == strategy_id,
            StrategyConfig.user_id == user_id,
        ).first()
        if not strategy:
            return False
        self.db.delete(strategy)
        self.db.commit()
        return True
