"""Crypto request / response schemas."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Filter / list
# ---------------------------------------------------------------------------


class CryptoListParams(BaseModel):
    """Query parameters for the crypto list endpoint."""

    market: str | None = Field(
        default="CRYPTO", description="Market filter (default: CRYPTO)"
    )
    exchange: str | None = Field(
        default=None, description="Exchange filter (e.g. BINANCE)"
    )
    category: str | None = Field(
        default=None, description="Category filter (e.g. Layer1, DeFi)"
    )
    search: str | None = Field(
        default=None, description="Search by code or name"
    )
    sort_by: str = Field(
        default="name", description="Sort field (name, price, change_24h)"
    )
    sort_order: str = Field(
        default="asc", description="Sort direction (asc, desc)"
    )
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(
        default=50, ge=1, le=200, description="Items per page"
    )


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------


class CryptoInfoOut(BaseModel):
    """Summary row returned in the crypto list."""

    code: str
    name: str
    name_zh: str | None = None
    exchange: str | None = None
    market: str | None = None
    category: str | None = None
    currency: str | None = None
    instrument_type: str | None = None
    status: str | None = None

    price: float | None = None
    change_24h: float | None = None
    # Canonical 24hr percentage change (same value as change_24h).
    # Prefer this in new code; change_24h is preserved for backward compat.
    change_pct: float | None = None
    volume_24h: float | None = None
    # Timestamp when the live price was fetched from the upstream provider.
    last_updated: datetime | None = None

    class Config:
        from_attributes = True


class CryptoListResponse(BaseModel):
    """Paginated crypto list response."""

    items: list[CryptoInfoOut]
    total: int
    page: int
    page_size: int


class DailyBarOut(BaseModel):
    """A single OHLCV row."""

    trade_date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    amount: float | None = None
    change_pct: float | None = None


class IndicatorOut(BaseModel):
    """Latest indicator summary."""

    etf_code: str
    trade_date: date | None = None
    ma5: float | None = None
    ma10: float | None = None
    ma20: float | None = None
    ma60: float | None = None
    rsi14: float | None = None
    macd_dif: float | None = None
    macd_dea: float | None = None
    macd_hist: float | None = None
    atr14: float | None = None
    bb_upper: float | None = None
    bb_lower: float | None = None
    volatility_20d: float | None = None
    volatility_60d: float | None = None
    max_drawdown_1y: float | None = None
    sharpe_1y: float | None = None
    return_1w: float | None = None
    return_1m: float | None = None
    return_3m: float | None = None
    return_6m: float | None = None
    return_1y: float | None = None

    class Config:
        from_attributes = True


class IndicatorHistoryOut(BaseModel):
    """Multiple indicator records for charting."""

    items: list[IndicatorOut]
    count: int


class CryptoDetailOut(BaseModel):
    """Full instrument detail including latest price and indicators."""

    code: str
    name: str
    name_zh: str | None = None
    exchange: str | None = None
    market: str | None = None
    category: str | None = None
    currency: str | None = None
    instrument_type: str | None = None
    status: str | None = None

    price: float | None = None
    change_24h: float | None = None
    # Canonical 24hr percentage change. Same value as change_24h;
    # change_24h is preserved as a deprecated alias for backward compat.
    change_pct: float | None = None
    high_24h: float | None = None
    low_24h: float | None = None
    volume_24h: float | None = None
    amount_24h: float | None = None

    latest_indicator: IndicatorOut | None = None

    class Config:
        from_attributes = True
