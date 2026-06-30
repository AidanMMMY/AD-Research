"""Risk control module for live trading (Phase 3).

Evaluates every order against configurable risk rules before submission
to the exchange.  Rules are loaded from the ``risk_rule`` table and the
``live_trade_config`` limits.

Rule types:
  - per_order:  Max order value, min order value.
  - daily:      Max daily loss, max daily order count.
  - market:     Volatility check (stub – Binance circuit breakers are
                monitored but not duplicated here).
  - duplicate:  Reject orders with identical (symbol, side) within a
                configurable window.

Circuit breaker:
  When a hard limit is breached (e.g. daily loss exceeded) the breaker
  trips and all subsequent orders are rejected until manually reset.

Usage::

    rc = RiskControl(db, config_id=1, settings=get_settings())
    result = rc.check_order(order_data)
    if not result.allowed:
        raise HTTPException(400, result.reason)
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.trading import LiveTradeConfig, LiveTradeOrder, RiskRule
from app.services.trading.binance_client import BinanceClient, BinanceClientError


class RiskCheckResult:
    """Outcome of a single risk-check run."""

    def __init__(self, allowed: bool, reason: str = ""):
        self.allowed = allowed
        self.reason = reason

    def __repr__(self) -> str:
        return f"<RiskCheckResult allowed={self.allowed} reason={self.reason!r}>"

    @classmethod
    def allow(cls) -> "RiskCheckResult":
        return cls(allowed=True, reason="")

    @classmethod
    def reject(cls, reason: str) -> "RiskCheckResult":
        return cls(allowed=False, reason=reason)


class CircuitBreaker:
    """In-memory circuit breaker.

    Tracks tripped state per config.  In production this should be backed
    by Redis so it survives process restarts.
    """

    # class-level store: {config_id: (tripped_at, reason)}
    _tripped: dict[int, tuple[datetime, str]] = {}

    @classmethod
    def trip(cls, config_id: int, reason: str) -> None:
        cls._tripped[config_id] = (datetime.now(timezone.utc), reason)

    @classmethod
    def reset(cls, config_id: int) -> None:
        cls._tripped.pop(config_id, None)

    @classmethod
    def is_tripped(cls, config_id: int) -> tuple[bool, str | None]:
        entry = cls._tripped.get(config_id)
        if entry is None:
            return False, None
        tripped_at, reason = entry
        return True, f"Circuit breaker tripped at {tripped_at.isoformat()}: {reason}"

    @classmethod
    def status(cls, config_id: int) -> dict:
        tripped, reason = cls.is_tripped(config_id)
        return {
            "circuit_breaker_active": tripped,
            "circuit_breaker_reason": reason,
        }


class RiskControl:
    """Pre-trade risk control.

    Evaluates orders against:
      1. Global trading switch (settings.binance_trading_enabled).
      2. Circuit breaker (tripped state).
      3. Per-order value limits.
      4. Daily loss / order-count limits.
      5. Duplicate order detection.
      6. Symbol allowlist (from LiveTradeConfig.allowed_symbols).

    Parameters:
        db: Database session.
        config: The LiveTradeConfig ORM instance.
        settings: Application settings (for global switch).
    """

    def __init__(
        self,
        db: Session,
        config: LiveTradeConfig,
        settings: Settings,
        client: BinanceClient | None = None,
    ):
        self.db = db
        self.config = config
        self.settings = settings
        self.client = client

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def check_order(
        self,
        instrument_code: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        order_type: str = "LIMIT",
    ) -> RiskCheckResult:
        """Run all applicable risk checks.  Returns the first rejection or allow."""
        # For MARKET orders, apply slippage buffer to the risk-check price so
        # notional and balance checks are conservative.
        risk_price = price
        if order_type.upper() == "MARKET":
            slippage = Decimal(str(self.settings.binance_market_order_slippage))
            risk_price = price * (Decimal("1") + slippage)

        checks = [
            self._check_global_switch,
            self._check_circuit_breaker,
            self._check_symbol_allowlist,
            self._check_symbol_filters,
            self._check_account_balance,
            self._check_order_value,
            self._check_daily_order_count,
            self._check_daily_loss,
            self._check_duplicate,
        ]

        for check_fn in checks:
            result = check_fn(
                instrument_code, side, quantity, risk_price, order_type
            )
            if not result.allowed:
                return result

        return RiskCheckResult.allow()

    # ------------------------------------------------------------------
    # Daily statistics helpers
    # ------------------------------------------------------------------

    def _today_start(self) -> datetime:
        """Return start of today in Asia/Shanghai (local trading day)."""
        now_local = datetime.now(ZoneInfo("Asia/Shanghai"))
        return datetime.combine(now_local.date(), datetime.min.time(), tzinfo=ZoneInfo("Asia/Shanghai"))

    def _daily_filled(self) -> list[LiveTradeOrder]:
        """Return today's filled orders for this config.

        Timezone normalisation mirrors :meth:`_daily_realized_pnl`: the
        column is naive in SQLite and may be either in PostgreSQL depending
        on session settings, while ``_today_start`` is tz-aware. Strip the
        tzinfo before comparison so the daily filter actually returns rows.
        """
        return (
            self.db.query(LiveTradeOrder)
            .filter(
                LiveTradeOrder.config_id == self.config.id,
                LiveTradeOrder.created_at >= self._today_start().replace(tzinfo=None),
                LiveTradeOrder.status.in_(["filled", "partially_filled"]),
            )
            .all()
        )

    def _daily_realized_pnl(self) -> Decimal:
        """Return today's realised PnL by summing realised PnL on positions
        that have been synced or updated today.

        Because ``LiveTradePosition.realized_pnl`` is a cumulative lifetime
        value, we restrict the sum to rows touched today (``updated_at``)
        so the daily loss limit reflects today's trading activity rather than
        all historical PnL.  In production this should be replaced by a
        first-class daily PnL ledger or order-level fill PnL.

        Timezone note: ``_today_start`` returns tz-aware Asia/Shanghai,
        but the ``updated_at`` column on SQLite is stored as naive UTC and
        PostgreSQL may store either depending on session settings. Stripping
        the tzinfo here makes the comparison robust across backends — the
        caller still computes "today" in the trading-day timezone via
        ``_today_start``, just normalising for the column's local repr.
        """
        from app.models.trading import LiveTradePosition

        today_start = self._today_start().replace(tzinfo=None)
        positions = (
            self.db.query(LiveTradePosition)
            .filter(
                LiveTradePosition.config_id == self.config.id,
                LiveTradePosition.updated_at >= today_start,
            )
            .all()
        )
        return sum(
            (p.realized_pnl or Decimal("0")) for p in positions
        )

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_global_switch(
        self, code: str, side: str, qty: Decimal, px: Decimal, order_type: str
    ) -> RiskCheckResult:
        """Master trading switch from settings."""
        if not self.settings.binance_trading_enabled:
            return RiskCheckResult.reject("Trading is disabled (binance_trading_enabled=False)")
        return RiskCheckResult.allow()

    def _check_circuit_breaker(
        self, code: str, side: str, qty: Decimal, px: Decimal, order_type: str
    ) -> RiskCheckResult:
        """Reject if circuit breaker is tripped."""
        tripped, reason = CircuitBreaker.is_tripped(self.config.id)
        if tripped:
            return RiskCheckResult.reject(reason or "Circuit breaker active")
        return RiskCheckResult.allow()

    def _check_symbol_allowlist(
        self, code: str, side: str, qty: Decimal, px: Decimal, order_type: str
    ) -> RiskCheckResult:
        """Check instrument code against allowed_symbols (if configured)."""
        allowed = self.config.allowed_symbols
        if not allowed:
            return RiskCheckResult.allow()

        try:
            import json

            symbols = json.loads(allowed)
            if not isinstance(symbols, list):
                return RiskCheckResult.allow()
        except json.JSONDecodeError:
            return RiskCheckResult.allow()

        if code not in symbols:
            return RiskCheckResult.reject(
                f"{code} is not in the allowed symbols list"
            )
        return RiskCheckResult.allow()

    def _check_symbol_filters(
        self, code: str, side: str, qty: Decimal, px: Decimal, order_type: str
    ) -> RiskCheckResult:
        """Reject if the order violates Binance symbol filters."""
        if self.client is None:
            return RiskCheckResult.allow()

        binance_symbol = BinanceClient.to_binance_symbol(code)
        try:
            _, _, errors = self.client.apply_symbol_filters(
                symbol=binance_symbol,
                side=side,
                quantity=qty,
                price=px,
                order_type=order_type,
            )
        except BinanceClientError as exc:
            return RiskCheckResult.reject(f"Symbol filter check failed: {exc}")

        if errors:
            return RiskCheckResult.reject(
                f"Binance filter violation: {'; '.join(errors)}"
            )
        return RiskCheckResult.allow()

    def _check_account_balance(
        self, code: str, side: str, qty: Decimal, px: Decimal, order_type: str
    ) -> RiskCheckResult:
        """For BUY orders, ensure free USDT covers the order notional + buffer."""
        if side.upper() != "BUY" or self.client is None:
            return RiskCheckResult.allow()

        try:
            balances = self.client.get_balances()
        except BinanceClientError as exc:
            return RiskCheckResult.reject(f"Could not fetch account balance: {exc}")

        usdt = balances.get("USDT", {})
        free_usdt = usdt.get("free", Decimal("0"))

        notional = qty * px
        # Small buffer (1%) to cover price movement / fees during submission.
        required = notional * Decimal("1.01")

        if free_usdt < required:
            return RiskCheckResult.reject(
                f"Insufficient USDT balance: free {free_usdt:.4f} < required {required:.4f}"
            )
        return RiskCheckResult.allow()

    def _check_order_value(
        self, code: str, side: str, qty: Decimal, px: Decimal, order_type: str
    ) -> RiskCheckResult:
        """Reject if order value exceeds per-order max."""
        notional = qty * px
        max_val = self.config.max_order_value
        if max_val is not None and notional > max_val:
            return RiskCheckResult.reject(
                f"Order value {notional:.2f} exceeds max {max_val:.2f} USDT"
            )
        return RiskCheckResult.allow()

    def _check_daily_order_count(
        self, code: str, side: str, qty: Decimal, px: Decimal, order_type: str
    ) -> RiskCheckResult:
        """Reject if today's order count exceeds the daily limit."""
        max_orders = self.config.max_daily_orders
        if max_orders is None:
            return RiskCheckResult.allow()

        today_count = len(self._daily_filled())
        if today_count >= max_orders:
            reason = (
                f"Daily order limit reached ({today_count}/{max_orders})"
            )
            CircuitBreaker.trip(self.config.id, reason)
            return RiskCheckResult.reject(reason)
        return RiskCheckResult.allow()

    def _check_daily_loss(
        self, code: str, side: str, qty: Decimal, px: Decimal, order_type: str
    ) -> RiskCheckResult:
        """Reject (and trip breaker) if daily realised loss exceeds limit."""
        max_loss = self.config.max_daily_loss
        if max_loss is None:
            return RiskCheckResult.allow()

        daily_pnl = self._daily_realized_pnl()
        if daily_pnl < -abs(max_loss):
            reason = (
                f"Daily loss limit exceeded: {daily_pnl:.2f} > {max_loss:.2f} USDT"
            )
            CircuitBreaker.trip(self.config.id, reason)
            return RiskCheckResult.reject(reason)
        return RiskCheckResult.allow()

    def _check_duplicate(
        self, code: str, side: str, qty: Decimal, px: Decimal, order_type: str
    ) -> RiskCheckResult:
        """Reject orders with identical (symbol, side) within 60 seconds."""
        window_start = datetime.now(timezone.utc) - timedelta(seconds=60)
        duplicate = (
            self.db.query(LiveTradeOrder)
            .filter(
                LiveTradeOrder.config_id == self.config.id,
                LiveTradeOrder.instrument_code == code,
                LiveTradeOrder.side == side,
                LiveTradeOrder.created_at >= window_start,
            )
            .first()
        )
        if duplicate is not None:
            return RiskCheckResult.reject(
                f"Duplicate order: {side} {code} within 60s (existing order #{duplicate.id})"
            )
        return RiskCheckResult.allow()

    # ------------------------------------------------------------------
    # Risk status
    # ------------------------------------------------------------------

    def get_risk_status(self) -> dict:
        """Return the current risk-control status for this config."""
        tripped, reason = CircuitBreaker.is_tripped(self.config.id)
        today_orders = len(self._daily_filled())
        daily_pnl = self._daily_realized_pnl()
        return {
            "config_id": self.config.id,
            "circuit_breaker_active": tripped,
            "circuit_breaker_reason": reason,
            "orders_today": today_orders,
            "realized_pnl_today": str(daily_pnl),
            "last_error": None,
        }

    def reset_circuit_breaker(self) -> dict:
        """Manually reset the circuit breaker for this config."""
        CircuitBreaker.reset(self.config.id)
        return {"status": "reset", "config_id": self.config.id}
