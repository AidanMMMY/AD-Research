"""Signal service for persistence and queries."""

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models.etf import ETFInfo
from app.models.etl import Signal, StrategyConfig
from app.services.strategy_engine import run_strategy_on_instrument, run_strategy_on_universe


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
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Generate and persist signals for a single instrument."""
        signals = run_strategy_on_instrument(
            db=self.db,
            etf_code=etf_code,
            strategy_type=strategy_type,
            params=params,
            trade_date=trade_date,
        )

        persisted = []
        seen_keys = set()
        for sig in signals:
            # Deduplicate within this batch by (strategy, code, date, type)
            key = (strategy_id, etf_code, trade_date, sig.get("type"))
            if key in seen_keys:
                continue
            seen_keys.add(key)

            persisted.extend(
                self._persist_signal(strategy_id, etf_code, trade_date, sig, params, user_id=user_id)
            )

        if persisted:
            self.db.commit()
        return persisted

    def generate_signals_universe(
        self,
        strategy_id: int,
        etf_codes: list[str],
        strategy_type: str,
        params: dict[str, Any],
        trade_date: date,
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Generate and persist signals for a cross-sectional strategy."""
        signals = run_strategy_on_universe(
            db=self.db,
            etf_codes=etf_codes,
            strategy_type=strategy_type,
            params=params,
            trade_date=trade_date,
        )

        persisted = []
        seen_keys = set()
        for sig in signals:
            etf_code = sig.get("etf_code")
            if not etf_code:
                continue

            key = (strategy_id, etf_code, trade_date, sig.get("type"))
            if key in seen_keys:
                continue
            seen_keys.add(key)

            persisted.extend(
                self._persist_signal(strategy_id, etf_code, trade_date, sig, params, user_id=user_id)
            )

        if persisted:
            self.db.commit()
        return persisted

    def _persist_signal(
        self,
        strategy_id: int,
        etf_code: str,
        trade_date: date,
        sig: dict[str, Any],
        params: dict[str, Any],
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Persist a single signal if it does not already exist.

        The signal table has a unique constraint on
        (strategy_id, etf_code, trade_date), so we skip if any signal already
        exists for that key regardless of type.
        """
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
            return []

        signal = Signal(
            user_id=user_id,
            strategy_id=strategy_id,
            etf_code=etf_code,
            trade_date=trade_date,
            signal_type=sig["type"],
            strength=sig.get("strength", 50),
            extra_data={**params, **sig.get("metadata", {})},
        )
        self.db.add(signal)
        return [{
            "strategy_id": strategy_id,
            "etf_code": etf_code,
            "trade_date": trade_date.isoformat(),
            "signal_type": sig["type"],
            "strength": sig.get("strength", 50),
        }]

    def get_signals(
        self,
        strategy_id: int | None = None,
        etf_code: str | None = None,
        trade_date: date | None = None,
        limit: int = 100,
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get signals with optional filtering."""
        query = self.db.query(Signal, ETFInfo, StrategyConfig).outerjoin(
            ETFInfo, Signal.etf_code == ETFInfo.code
        ).outerjoin(
            StrategyConfig, Signal.strategy_id == StrategyConfig.id
        )
        if user_id:
            # System-generated signals have user_id NULL and are visible to everyone.
            query = query.filter(
                (Signal.user_id == user_id) | (Signal.user_id.is_(None))
            )
        if strategy_id:
            query = query.filter(Signal.strategy_id == strategy_id)
        if etf_code:
            query = query.filter(Signal.etf_code == etf_code)
        if trade_date:
            query = query.filter(Signal.trade_date == trade_date)

        rows = query.order_by(Signal.created_at.desc()).limit(limit).all()
        return [
            {
                "id": sig.id,
                "strategy_id": sig.strategy_id,
                "strategy_name": strat.name if strat else None,
                "strategy_type": strat.strategy_type if strat else None,
                "etf_code": sig.etf_code,
                "etf_name": etf.name if etf else None,
                "name_zh": etf.name_zh if etf else None,
                "trade_date": sig.trade_date.isoformat() if sig.trade_date else None,
                "signal_type": sig.signal_type,
                "strength": sig.strength,
                "extra_data": sig.extra_data,
                "created_at": sig.created_at.isoformat() if sig.created_at else None,
            }
            for sig, etf, strat in rows
        ]

    def get_signals_for_etf(
        self,
        etf_code: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get recent trading signals for a single instrument.

        Thin convenience wrapper around :meth:`get_signals` so the crypto
        detail page has a stable, instrument-scoped entry point.
        """
        return self.get_signals(etf_code=etf_code, limit=limit)

    def get_latest_signals(self, limit: int = 50, user_id: int | None = None) -> list[dict[str, Any]]:
        """Get the latest signals, optionally filtered by user."""
        return self.get_signals(limit=limit, user_id=user_id)
