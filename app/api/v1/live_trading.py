"""Live trading API endpoints (Phase 3).

Low-risk (read-only):
  GET  /configs                          — list trade configs
  POST /configs                          — create config (encrypts credentials)
  PUT  /configs/{id}                     — update config
  DELETE /configs/{id}                   — remove config
  GET  /configs/{id}/account             — Binance account balances
  GET  /configs/{id}/positions           — synced positions
  GET  /configs/{id}/orders              — order history
  GET  /configs/{id}/trades              — trade history

Medium-risk (write):
  POST   /configs/{id}/orders            — place order (risk-checked)
  DELETE /configs/{id}/orders/{order_id} — cancel order

Risk control:
  GET  /configs/{id}/risk-status         — current risk state
  POST /configs/{id}/circuit-breaker/reset  — reset breaker (admin)
  GET  /risk-rules                       — list risk rules
"""

import base64
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.config import get_settings
from app.models.trading import (
    LiveTradeConfig,
    LiveTradeOrder,
    LiveTradePosition,
    RiskRule,
)
from app.models.etf import ETFInfo
from app.schemas.auth import UserResponse
from app.schemas.trading import (
    LiveAccountOut,
    LiveConfigCreate,
    LiveConfigOut,
    LiveConfigUpdate,
    LiveOrderCreate,
    LiveOrderOut,
    LivePositionOut,
    RiskRuleOut,
    RiskStatusOut,
)
from app.services.risk_control import CircuitBreaker, RiskControl
from app.services.trading.binance_client import BinanceClient, BinanceClientError

router = APIRouter()

# Prefix for encrypted values in the database
_ENCRYPTED_PREFIX = "enc:"


# ---------------------------------------------------------------------------
# Owner-scope helpers
# ---------------------------------------------------------------------------

def _get_config_for_user(
    db: Session,
    config_id: int,
    current_user: UserResponse,
) -> LiveTradeConfig | None:
    """Get a config by ID, enforcing owner-scope.

    - If config.user_id is NULL (legacy), allow any authenticated user.
    - If config.user_id is set, require config.user_id == current_user.id.
    Returns None if not found or access denied (caller should return 404).
    """
    config = db.query(LiveTradeConfig).filter(LiveTradeConfig.id == config_id).first()
    if not config:
        return None
    # Legacy configs (user_id=NULL) are accessible to all authenticated users
    if config.user_id is not None and config.user_id != current_user.id:
        return None
    return config


# ---------------------------------------------------------------------------
# Fernet helpers (same pattern as NotificationService)
# ---------------------------------------------------------------------------

def _get_fernet() -> Fernet | None:
    """Build a Fernet instance from the configured encryption key."""
    from app.config import auth_settings

    settings = get_settings()
    key = settings.notification_encryption_key or auth_settings.SECRET_KEY
    if not key:
        return None
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    encoded = base64.urlsafe_b64encode(digest)
    return Fernet(encoded)


def _encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret value for storage."""
    fernet = _get_fernet()
    if fernet is None:
        raise HTTPException(status_code=500, detail="Encryption key not configured")
    token = fernet.encrypt(plaintext.encode("utf-8"))
    return _ENCRYPTED_PREFIX + token.decode("utf-8")


def _decrypt_secret(ciphertext: str | None) -> str | None:
    """Decrypt a stored secret value."""
    if not ciphertext or not ciphertext.startswith(_ENCRYPTED_PREFIX):
        return ciphertext
    fernet = _get_fernet()
    if fernet is None:
        return None
    token = ciphertext[len(_ENCRYPTED_PREFIX):].encode("utf-8")
    try:
        return fernet.decrypt(token).decode("utf-8")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def _make_binance_client(config: LiveTradeConfig) -> BinanceClient:
    """Build a BinanceClient from a LiveTradeConfig (decrypting credentials)."""
    api_key = _decrypt_secret(config.api_key_encrypted) or ""
    api_secret = _decrypt_secret(config.api_secret_encrypted) or ""
    if not api_key or not api_secret:
        raise HTTPException(status_code=400, detail="API credentials not configured")
    return BinanceClient(
        api_key=api_key,
        api_secret=api_secret,
        testnet=config.is_testnet,
    )


# ---------------------------------------------------------------------------
# Config CRUD
# ---------------------------------------------------------------------------

@router.get("/configs", response_model=list[LiveConfigOut])
def list_configs(
    db: Session = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    """List live-trade configurations owned by or shared with the current user.

    - Legacy configs (user_id=NULL) are visible to all users.
    - User-owned configs are filtered by current_user.id.
    """
    # Show user's own configs + legacy configs (user_id=NULL)
    configs = (
        db.query(LiveTradeConfig)
        .filter(
            (LiveTradeConfig.user_id == current_user.id) | (LiveTradeConfig.user_id.is_(None))
        )
        .order_by(LiveTradeConfig.created_at.desc())
        .all()
    )
    return [LiveConfigOut.model_validate(c) for c in configs]


@router.post("/configs", response_model=LiveConfigOut, status_code=201)
def create_config(
    payload: LiveConfigCreate,
    db: Session = Depends(get_db),
    current_user: UserResponse = Depends(require_admin),
):
    """Create a new live-trade configuration (admin only).

    API key and secret are encrypted at rest with Fernet before storage.
    The config is owned by the current admin user.
    """
    config = LiveTradeConfig(
        user_id=current_user.id,
        name=payload.name,
        api_key_encrypted=_encrypt_secret(payload.api_key),
        api_secret_encrypted=_encrypt_secret(payload.api_secret),
        is_testnet=payload.is_testnet,
        is_enabled=False,  # always start disabled
        max_order_value=payload.max_order_value,
        max_daily_loss=payload.max_daily_loss,
        max_daily_orders=payload.max_daily_orders,
        allowed_symbols=payload.allowed_symbols,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return LiveConfigOut.model_validate(config)


@router.put("/configs/{config_id}", response_model=LiveConfigOut)
def update_config(
    config_id: int,
    payload: LiveConfigUpdate,
    db: Session = Depends(get_db),
    current_user: UserResponse = Depends(require_admin),
):
    """Update a live-trade configuration (admin only, owner-scoped).

    Secrets are NOT updatable via this endpoint — recreate the config instead.
    """
    config = _get_config_for_user(db, config_id, current_user)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(config, key, value)

    db.commit()
    db.refresh(config)
    return LiveConfigOut.model_validate(config)


@router.delete("/configs/{config_id}", status_code=204)
def delete_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: UserResponse = Depends(require_admin),
):
    """Delete a live-trade configuration (admin only, owner-scoped)."""
    config = _get_config_for_user(db, config_id, current_user)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    db.delete(config)
    db.commit()


# ---------------------------------------------------------------------------
# Read-only: account / positions / orders / trades
# ---------------------------------------------------------------------------

@router.get("/configs/{config_id}/account", response_model=LiveAccountOut)
def get_account(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    """Fetch live Binance account balances (owner-scoped)."""
    config = _get_config_for_user(db, config_id, current_user)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    client = _make_binance_client(config)
    try:
        info = client.get_account_info()
    except BinanceClientError as exc:
        raise HTTPException(status_code=502, detail=f"Binance API error: {exc}")

    # Simplify balances for the response
    balances = []
    for b in info.get("balances", []):
        free = Decimal(b.get("free", "0"))
        locked = Decimal(b.get("locked", "0"))
        total = free + locked
        if total > 0:
            balances.append({
                "asset": b["asset"],
                "free": str(free),
                "locked": str(locked),
                "total": str(total),
            })

    return LiveAccountOut(
        balances=balances,
        can_trade=info.get("canTrade", False),
        account_type=info.get("accountType"),
    )


@router.get("/configs/{config_id}/positions", response_model=list[LivePositionOut])
def list_positions(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    """Return synced live-trade positions for a config (owner-scoped)."""
    config = _get_config_for_user(db, config_id, current_user)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    # Sync positions from Binance before returning
    _sync_positions_from_binance(db, config)

    positions = (
        db.query(LiveTradePosition)
        .filter(
            LiveTradePosition.config_id == config_id,
            LiveTradePosition.quantity > 0,
        )
        .all()
    )
    _enrich_instrument_names(db, positions)
    return [LivePositionOut.model_validate(p) for p in positions]


@router.get("/configs/{config_id}/orders", response_model=list[LiveOrderOut])
def list_orders(
    config_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    """Return recent live-trade orders for a config (owner-scoped)."""
    config = _get_config_for_user(db, config_id, current_user)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    orders = (
        db.query(LiveTradeOrder)
        .filter(LiveTradeOrder.config_id == config_id)
        .order_by(LiveTradeOrder.created_at.desc())
        .limit(limit)
        .all()
    )
    _enrich_instrument_names(db, orders)
    return [LiveOrderOut.model_validate(o) for o in orders]


@router.get("/configs/{config_id}/trades")
def list_trades(
    config_id: int,
    symbol: str | None = Query(default=None, description="Binance symbol, e.g. BTCUSDT"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    """Fetch trade history directly from Binance (owner-scoped)."""
    config = _get_config_for_user(db, config_id, current_user)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    client = _make_binance_client(config)
    try:
        return client.get_trades(symbol=symbol, limit=limit)
    except BinanceClientError as exc:
        raise HTTPException(status_code=502, detail=f"Binance API error: {exc}")


# ---------------------------------------------------------------------------
# Write: place / cancel orders
# ---------------------------------------------------------------------------

@router.post("/configs/{config_id}/orders", response_model=LiveOrderOut, status_code=201)
def place_order(
    config_id: int,
    payload: LiveOrderCreate,
    db: Session = Depends(get_db),
    current_user: UserResponse = Depends(require_admin),
):
    """Place a live order on Binance (risk-checked, owner-scoped).

    The order passes through RiskControl before hitting the exchange.
    """
    config = _get_config_for_user(db, config_id, current_user)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    if not config.is_enabled:
        raise HTTPException(status_code=400, detail="Config is disabled")

    # Determine price for risk check
    binance_symbol = BinanceClient.to_binance_symbol(payload.instrument_code)
    client = _make_binance_client(config)

    if payload.price:
        risk_price = payload.price
    else:
        # MARKET order — fetch current price for risk check
        try:
            risk_price = client.get_ticker_price(binance_symbol)
            if risk_price is None or risk_price <= 0:
                raise HTTPException(status_code=502, detail="Could not fetch current price")
        except BinanceClientError as exc:
            raise HTTPException(status_code=502, detail=f"Binance API error: {exc}")

    # ── Apply Binance symbol filters before risk check and placement ──
    try:
        adjusted_qty, adjusted_price, filter_errors = client.apply_symbol_filters(
            symbol=binance_symbol,
            side=payload.side,
            quantity=payload.quantity,
            price=risk_price,
            order_type=payload.order_type,
        )
    except BinanceClientError as exc:
        raise HTTPException(status_code=502, detail=f"Binance filter check failed: {exc}")

    if filter_errors:
        raise HTTPException(
            status_code=400,
            detail=f"Symbol filter violation: {'; '.join(filter_errors)}",
        )

    # ── Risk check ──
    rc = RiskControl(db, config, get_settings(), client=client)
    risk_result = rc.check_order(
        instrument_code=payload.instrument_code,
        side=payload.side,
        quantity=adjusted_qty,
        price=adjusted_price if payload.price else risk_price,
        order_type=payload.order_type,
    )
    if not risk_result.allowed:
        raise HTTPException(status_code=400, detail=f"Risk check failed: {risk_result.reason}")

    # ── Place order on Binance ──
    try:
        place_kwargs: dict[str, Any] = {
            "symbol": binance_symbol,
            "side": payload.side,
            "quantity": adjusted_qty,
            "order_type": payload.order_type,
        }
        if payload.order_type.upper() != "MARKET":
            place_kwargs["price"] = adjusted_price
        binance_order = client.place_order(**place_kwargs)
    except BinanceClientError as exc:
        raise HTTPException(status_code=502, detail=f"Binance order failed: {exc}")

    # ── Record in local DB ──
    recorded_price = (
        adjusted_price if payload.price and adjusted_price != payload.price
        else payload.price or Decimal(str(binance_order.get("price", risk_price)))
    )
    order = LiveTradeOrder(
        config_id=config_id,
        order_id_from_exchange=str(binance_order.get("orderId", "")),
        instrument_code=payload.instrument_code,
        side=payload.side,
        order_type=payload.order_type,
        price=recorded_price,
        quantity=adjusted_qty,
        filled_quantity=Decimal(str(binance_order.get("executedQty", "0"))),
        status=binance_order.get("status", "pending").lower(),
        signal_id=payload.signal_id,
        raw_response=json.dumps(binance_order, default=str),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    _enrich_instrument_names(db, [order])
    return LiveOrderOut.model_validate(order)


@router.delete("/configs/{config_id}/orders/{order_id}", status_code=204)
def cancel_order(
    config_id: int,
    order_id: int,
    db: Session = Depends(get_db),
    current_user: UserResponse = Depends(require_admin),
):
    """Cancel an open order (owner-scoped, first on Binance, then mark locally)."""
    config = _get_config_for_user(db, config_id, current_user)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    local_order = (
        db.query(LiveTradeOrder)
        .filter(LiveTradeOrder.id == order_id, LiveTradeOrder.config_id == config_id)
        .first()
    )
    if not local_order:
        raise HTTPException(status_code=404, detail="Order not found")

    if local_order.status not in ("pending", "partially_filled", "new"):
        raise HTTPException(status_code=400, detail=f"Order status {local_order.status} cannot be cancelled")

    client = _make_binance_client(config)
    binance_symbol = BinanceClient.to_binance_symbol(local_order.instrument_code)

    try:
        if local_order.order_id_from_exchange:
            client.cancel_order(binance_symbol, local_order.order_id_from_exchange)
    except BinanceClientError as exc:
        raise HTTPException(status_code=502, detail=f"Binance cancel failed: {exc}")

    local_order.status = "cancelled"
    db.commit()


# ---------------------------------------------------------------------------
# Risk control
# ---------------------------------------------------------------------------

@router.get("/configs/{config_id}/risk-status", response_model=RiskStatusOut)
def get_risk_status(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    """Return the current risk-control status for a config (owner-scoped)."""
    config = _get_config_for_user(db, config_id, current_user)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    rc = RiskControl(db, config, get_settings())
    return rc.get_risk_status()


@router.post("/configs/{config_id}/circuit-breaker/reset")
def reset_circuit_breaker(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: UserResponse = Depends(require_admin),
):
    """Manually reset the circuit breaker (admin only, owner-scoped)."""
    config = _get_config_for_user(db, config_id, current_user)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    rc = RiskControl(db, config, get_settings())
    return rc.reset_circuit_breaker()


@router.get("/risk-rules", response_model=list[RiskRuleOut])
def list_risk_rules(
    db: Session = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    """List all configured risk rules."""
    rules = db.query(RiskRule).filter(RiskRule.user_id == current_user.id).order_by(RiskRule.id).all()
    return [RiskRuleOut.model_validate(r) for r in rules]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sync_positions_from_binance(db: Session, config: LiveTradeConfig) -> None:
    """Sync on-exchange balances to local LiveTradePosition rows.

    For simplicity, we treat each non-zero spot balance as a "position"
    with avg_cost=0 (Binance does not expose per-symbol avg cost via
    the REST API; users can manually enter cost basis if needed).
    """
    try:
        client = _make_binance_client(config)
        balances = client.get_balances()
    except Exception:
        return

    # Remove USDT itself (quote currency, not a position)
    usdt_info = balances.pop("USDT", None)

    for asset, info in balances.items():
        code = BinanceClient.from_binance_symbol(asset + "USDT")
        qty = info["total"]

        # Fetch current price
        try:
            price = client.get_ticker_price(asset + "USDT")
        except Exception:
            price = None

        position = (
            db.query(LiveTradePosition)
            .filter(
                LiveTradePosition.config_id == config.id,
                LiveTradePosition.instrument_code == code,
            )
            .first()
        )

        if position is None:
            position = LiveTradePosition(
                config_id=config.id,
                instrument_code=code,
                quantity=qty,
                avg_cost=Decimal("0"),  # not tracked by Binance REST
            )
            db.add(position)
        else:
            position.quantity = qty

        position.current_price = price
        if price is not None and qty > 0:
            position.market_value = qty * price
            position.unrealized_pnl = qty * (price - position.avg_cost)

    db.commit()


def _enrich_instrument_names(db: Session, items: list[Any]) -> None:
    """Set ``instrument_name`` on order/position objects from ETFInfo."""
    if not items:
        return
    codes = {getattr(item, "instrument_code", None) for item in items}
    codes.discard(None)
    if not codes:
        return
    rows = (
        db.query(ETFInfo.code, ETFInfo.name)
        .filter(ETFInfo.code.in_(list(codes)))
        .all()
    )
    names = {r.code: r.name for r in rows}
    for item in items:
        code = getattr(item, "instrument_code", None)
        item.instrument_name = names.get(code)
