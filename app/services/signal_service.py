"""Signal service for persistence and queries."""

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models.etl import Signal
from app.services.signal_generator import generate_signals_for_strategy


class SignalService:
    """Service for signal operations."""

    def __init__(self, db: Session):
        self.db = db

    def generate_signals(
        self,
        strategy_id: int,
        etf_code: str,
        strategy_type: str,
        params: dict[str, Any],
        trade_date: date,
    ) -> list[dict[str, Any]]:
        """Generate and persist signals for a strategy."""
        signals = generate_signals_for_strategy(
            db=self.db,
            etf_code=etf_code,
            strategy_type=strategy_type,
            params=params,
            trade_date=trade_date,
        )

        persisted = []
        for sig in signals:
            # Skip if a signal already exists for this (strategy, etf, date)
            existing = (
                self.db.query(Signal)
                .filter(
                    Signal.strategy_id == strategy_id,
                    Signal.etf_code == etf_code,
                    Signal.trade_date == trade_date,
                )
                .first()
            )
            if existing:
                continue

            signal = Signal(
                strategy_id=strategy_id,
                etf_code=etf_code,
                trade_date=trade_date,
                signal_type=sig["type"],
                strength=sig.get("strength", 50),
                extra_data=params,
            )
            self.db.add(signal)
            persisted.append({
                "strategy_id": strategy_id,
                "etf_code": etf_code,
                "trade_date": trade_date.isoformat(),
                "signal_type": sig["type"],
                "strength": sig.get("strength", 50),
            })

        if persisted:
            self.db.commit()
        return persisted

    def get_signals(
        self,
        strategy_id: int | None = None,
        etf_code: str | None = None,
        trade_date: date | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get signals with optional filtering."""
        query = self.db.query(Signal)
        if strategy_id:
            query = query.filter(Signal.strategy_id == strategy_id)
        if etf_code:
            query = query.filter(Signal.etf_code == etf_code)
        if trade_date:
            query = query.filter(Signal.trade_date == trade_date)

        results = query.order_by(Signal.created_at.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "strategy_id": r.strategy_id,
                "etf_code": r.etf_code,
                "trade_date": r.trade_date.isoformat() if r.trade_date else None,
                "signal_type": r.signal_type,
                "strength": r.strength,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in results
        ]

    def get_latest_signals(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get the latest signals."""
        # Get the most recent trade date
        latest = (
            self.db.query(Signal)
            .order_by(Signal.trade_date.desc())
            .first()
        )
        if not latest or not latest.trade_date:
            return []

        return self.get_signals(trade_date=latest.trade_date, limit=limit)
