"""Trading request / response schemas (Phase 2 – paper trading & Phase 3 – live)."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Phase 2 – Paper trading
# ---------------------------------------------------------------------------


class PaperAccountCreate(BaseModel):
    """Request body to create a new paper-trade account."""

    name: str = Field(..., max_length=100, description="Account label")
    initial_balance: Decimal = Field(
        default=Decimal("10000"), ge=100, description="Starting USDT balance"
    )


class PaperAccountOut(BaseModel):
    """Paper-trade account summary returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    initial_balance: Decimal
    cash: Decimal
    currency: str
    status: str
    created_at: datetime | None = None

    # Computed fields (filled by service)
    total_value: Decimal | None = None
    total_pnl: Decimal | None = None
    pnl_pct: Decimal | None = None


class PaperAccountListOut(BaseModel):
    """Paginated list of paper-trade accounts."""

    items: list[PaperAccountOut]
    total: int


# --- Orders ---


class PaperOrderCreate(BaseModel):
    """Request body to place a paper-trade order."""

    instrument_code: str = Field(..., max_length=20, description="e.g. BTC.US")
    order_type: str = Field(..., pattern="^(BUY|SELL)$", description="BUY or SELL")
    quantity: Decimal = Field(..., gt=0, description="Quantity in base asset")
    price: Decimal | None = Field(
        default=None, ge=0, description="Limit price; uses market price if omitted"
    )
    signal_id: int | None = Field(default=None, description="Associated signal (optional)")


class PaperOrderOut(BaseModel):
    """Paper-trade order returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    instrument_code: str
    order_type: str
    price: Decimal | None = None
    quantity: Decimal
    filled_quantity: Decimal
    status: str
    reject_reason: str | None = None
    signal_id: int | None = None
    created_at: datetime | None = None
    filled_at: datetime | None = None


class PaperOrderListOut(BaseModel):
    """Paginated list of paper-trade orders."""

    items: list[PaperOrderOut]
    total: int


# --- Positions ---


class PaperPositionOut(BaseModel):
    """Paper-trade position returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    instrument_code: str
    quantity: Decimal
    avg_cost: Decimal
    market_value: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    realized_pnl: Decimal | None = None
    updated_at: datetime | None = None

    # Enriched fields (filled by service from ETFInfo)
    instrument_name: str | None = None
    current_price: Decimal | None = None
    pnl_pct: Decimal | None = None


# --- PnL ---


class PnLSummaryOut(BaseModel):
    """Profit / loss summary for one account."""

    account_id: int
    total_equity: Decimal
    cash: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    total_pnl: Decimal
    pnl_pct: Decimal | None = None
    trade_count: int = 0
    win_count: int = 0
    win_rate: Decimal | None = None


# ---------------------------------------------------------------------------
# Phase 3 – Live trading
# ---------------------------------------------------------------------------


class LiveConfigCreate(BaseModel):
    """Request body to create a live-trade configuration."""

    name: str = Field(..., max_length=100)
    api_key: str = Field(..., max_length=128, description="Binance API key")
    api_secret: str = Field(..., max_length=128, description="Binance API secret")
    is_testnet: bool = True
    max_order_value: Decimal = Field(default=Decimal("100"), ge=0)
    max_daily_loss: Decimal = Field(default=Decimal("500"), ge=0)
    max_daily_orders: int = Field(default=20, ge=1, le=1000)
    allowed_symbols: str | None = Field(default=None, description="JSON array string")


class LiveConfigUpdate(BaseModel):
    """Request body to update a live-trade configuration (partial)."""

    name: str | None = Field(default=None, max_length=100)
    is_enabled: bool | None = None
    max_order_value: Decimal | None = Field(default=None, ge=0)
    max_daily_loss: Decimal | None = Field(default=None, ge=0)
    max_daily_orders: int | None = Field(default=None, ge=1, le=1000)
    allowed_symbols: str | None = None


class LiveConfigOut(BaseModel):
    """Live-trade configuration returned by the API (secrets are NEVER returned)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_testnet: bool
    is_enabled: bool
    max_order_value: Decimal
    max_daily_loss: Decimal
    max_daily_orders: int
    allowed_symbols: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LiveOrderOut(BaseModel):
    """Live-trade order returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    config_id: int
    order_id_from_exchange: str | None = None
    instrument_code: str
    side: str
    order_type: str
    price: Decimal | None = None
    quantity: Decimal
    filled_quantity: Decimal
    status: str
    reject_reason: str | None = None
    signal_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LivePositionOut(BaseModel):
    """Live-trade position returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    config_id: int
    instrument_code: str
    quantity: Decimal
    avg_cost: Decimal
    current_price: Decimal | None = None
    market_value: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    realized_pnl: Decimal | None = None
    updated_at: datetime | None = None


class LiveAccountOut(BaseModel):
    """Binance account summary."""

    balances: list[dict]
    can_trade: bool
    account_type: str | None = None


class LiveOrderCreate(BaseModel):
    """Request body to place a live-trade order."""

    instrument_code: str = Field(..., max_length=20)
    side: str = Field(..., pattern="^(BUY|SELL)$")
    order_type: str = Field(default="LIMIT", pattern="^(LIMIT|MARKET)$")
    quantity: Decimal = Field(..., gt=0)
    price: Decimal | None = Field(default=None, ge=0, description="Required for LIMIT orders")
    signal_id: int | None = None


class RiskStatusOut(BaseModel):
    """Current risk-control status for a live-trade config."""

    config_id: int
    circuit_breaker_active: bool
    circuit_breaker_reason: str | None = None
    orders_today: int = 0
    realized_pnl_today: Decimal = Decimal("0")
    last_error: str | None = None


class RiskRuleOut(BaseModel):
    """Risk rule returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    rule_type: str
    param_key: str
    param_value: str
    is_active: bool
