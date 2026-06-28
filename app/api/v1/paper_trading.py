"""Paper (simulated) trading API routes.

Account management, order placement, position tracking, and P&L endpoints.
All trades execute at live Binance prices but move no real funds.
"""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_paper_trading_service
from app.schemas.trading import (
    PaperAccountCreate,
    PaperAccountListOut,
    PaperAccountOut,
    PaperOrderCreate,
    PaperOrderListOut,
    PaperOrderOut,
    PaperPositionOut,
    PnLSummaryOut,
)
from app.services.paper_trading_service import PaperTradingError, PaperTradingService

router = APIRouter()


# ---------------------------------------------------------------------------
# Account endpoints
# ---------------------------------------------------------------------------


@router.get("/accounts", response_model=PaperAccountListOut)
def list_accounts(
    service: PaperTradingService = Depends(get_paper_trading_service),
):
    """List all active paper-trade accounts."""
    accounts = service.get_accounts()
    items = []
    for acct in accounts:
        try:
            pnl = service.get_pnl_summary(acct.id)
            total_value = pnl["total_equity"]
            total_pnl = pnl["total_pnl"]
            pnl_pct = pnl["pnl_pct"]
        except Exception:
            total_value = None
            total_pnl = None
            pnl_pct = None

        items.append(
            PaperAccountOut(
                id=acct.id,
                name=acct.name,
                initial_balance=acct.initial_balance,
                cash=acct.cash,
                currency=acct.currency,
                status=acct.status,
                created_at=acct.created_at,
                total_value=total_value,
                total_pnl=total_pnl,
                pnl_pct=pnl_pct,
            )
        )
    return PaperAccountListOut(items=items, total=len(items))


@router.post("/accounts", response_model=PaperAccountOut, status_code=status.HTTP_201_CREATED)
def create_account(
    data: PaperAccountCreate,
    service: PaperTradingService = Depends(get_paper_trading_service),
):
    """Create a new paper-trade account with an initial USDT balance."""
    account = service.create_account(
        name=data.name,
        initial_balance=data.initial_balance,
    )
    return PaperAccountOut(
        id=account.id,
        name=account.name,
        initial_balance=account.initial_balance,
        cash=account.cash,
        currency=account.currency,
        status=account.status,
        created_at=account.created_at,
        total_value=account.cash,
        total_pnl=Decimal("0"),
        pnl_pct=Decimal("0"),
    )


@router.get("/accounts/{account_id}", response_model=PaperAccountOut)
def get_account(
    account_id: int,
    service: PaperTradingService = Depends(get_paper_trading_service),
):
    """Get a single paper-trade account by ID."""
    account = service.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    try:
        pnl = service.get_pnl_summary(account.id)
    except Exception:
        pnl = None

    return PaperAccountOut(
        id=account.id,
        name=account.name,
        initial_balance=account.initial_balance,
        cash=account.cash,
        currency=account.currency,
        status=account.status,
        created_at=account.created_at,
        total_value=pnl["total_equity"] if pnl else account.cash,
        total_pnl=pnl["total_pnl"] if pnl else None,
        pnl_pct=pnl["pnl_pct"] if pnl else None,
    )


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: int,
    service: PaperTradingService = Depends(get_paper_trading_service),
):
    """Archive a paper-trade account (soft-delete)."""
    if not service.archive_account(account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    return None


# ---------------------------------------------------------------------------
# Order endpoints
# ---------------------------------------------------------------------------


@router.get("/accounts/{account_id}/orders", response_model=PaperOrderListOut)
def list_orders(
    account_id: int,
    limit: int = Query(50, ge=1, le=200),
    service: PaperTradingService = Depends(get_paper_trading_service),
):
    """List recent orders for an account, newest first."""
    # Verify account exists
    if not service.get_account(account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    orders = service.get_orders(account_id, limit=limit)
    return PaperOrderListOut(
        items=[PaperOrderOut.model_validate(o) for o in orders],
        total=len(orders),
    )


@router.post(
    "/accounts/{account_id}/orders",
    response_model=PaperOrderOut,
    status_code=status.HTTP_201_CREATED,
)
def place_order(
    account_id: int,
    data: PaperOrderCreate,
    service: PaperTradingService = Depends(get_paper_trading_service),
):
    """Place a simulated order (executes immediately at market price).

    Raises 400 on insufficient funds, unknown instrument, or other
    business-rule violations.
    """
    try:
        order = service.place_order(
            account_id=account_id,
            instrument_code=data.instrument_code,
            order_type=data.order_type,
            quantity=data.quantity,
            price=data.price,
            signal_id=data.signal_id,
        )
        return PaperOrderOut.model_validate(order)
    except PaperTradingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/accounts/{account_id}/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_order(
    account_id: int,
    order_id: int,
    service: PaperTradingService = Depends(get_paper_trading_service),
):
    """Cancel a pending order."""
    if not service.get_account(account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    if not service.cancel_order(order_id):
        raise HTTPException(status_code=404, detail="Order not found or already filled")
    return None


# ---------------------------------------------------------------------------
# Position endpoints
# ---------------------------------------------------------------------------


@router.get("/accounts/{account_id}/positions", response_model=list[PaperPositionOut])
def list_positions(
    account_id: int,
    service: PaperTradingService = Depends(get_paper_trading_service),
):
    """List current positions (quantity > 0) with live market values."""
    if not service.get_account(account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    positions = service.get_positions(account_id)
    return [
        PaperPositionOut(
            id=p.id,
            account_id=p.account_id,
            instrument_code=p.instrument_code,
            quantity=p.quantity,
            avg_cost=p.avg_cost,
            market_value=p.market_value,
            unrealized_pnl=p.unrealized_pnl,
            realized_pnl=p.realized_pnl,
            updated_at=p.updated_at,
            instrument_name=getattr(p, "instrument_name", None),
            current_price=getattr(p, "current_price", None),
            pnl_pct=getattr(p, "pnl_pct", None),
        )
        for p in positions
    ]


# ---------------------------------------------------------------------------
# PnL endpoints
# ---------------------------------------------------------------------------


@router.get("/accounts/{account_id}/pnl", response_model=PnLSummaryOut)
def get_pnl(
    account_id: int,
    service: PaperTradingService = Depends(get_paper_trading_service),
):
    """Get P&L summary for an account (refreshes market values first)."""
    try:
        result = service.get_pnl_summary(account_id)
        return PnLSummaryOut(
            account_id=result["account_id"],
            total_equity=result["total_equity"],
            cash=result["cash"],
            market_value=result["market_value"],
            unrealized_pnl=result["unrealized_pnl"],
            realized_pnl=result["realized_pnl"],
            total_pnl=result["total_pnl"],
            pnl_pct=result["pnl_pct"],
            trade_count=result["trade_count"],
            win_count=result["win_count"],
            win_rate=result["win_rate"],
        )
    except PaperTradingError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Market-value sync
# ---------------------------------------------------------------------------


@router.post("/accounts/{account_id}/sync")
def sync_market_values(
    account_id: int,
    service: PaperTradingService = Depends(get_paper_trading_service),
):
    """Update all position market values from Binance live prices."""
    if not service.get_account(account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    updated = service.update_market_values(account_id)
    return {"updated": updated}


# ---------------------------------------------------------------------------
# Auto-trade from signals
# ---------------------------------------------------------------------------


@router.post("/accounts/{account_id}/auto-trade", response_model=list[PaperOrderOut])
def auto_trade(
    account_id: int,
    trade_date: date = Query(None, description="Signal date (defaults to today)"),
    service: PaperTradingService = Depends(get_paper_trading_service),
):
    """Execute trades automatically based on today's signals.

    BUY signals allocate ~10% of equity; SELL signals close the full position.
    """
    if not service.get_account(account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    orders = service.auto_trade_from_signals(account_id, trade_date)
    return [PaperOrderOut.model_validate(o) for o in orders]
