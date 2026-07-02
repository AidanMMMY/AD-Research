"""Pydantic schemas for the futures API surface.

Covers contract metadata, daily OHLCV bars, dashboard aggregations,
and exchange leaderboards.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Contract metadata
# ---------------------------------------------------------------------------


class FuturesContractOut(BaseModel):
    """A row in the futures contract list."""

    code: str = Field(..., description="Main contract code, e.g. CU0")
    name: str = Field(..., description="Display name")
    exchange: str = Field(..., description="Exchange code: SHFE/DCE/CZCE/CFFEX/INE/GFEX")
    exchange_label: str | None = Field(None, description="Chinese exchange name")
    product: str = Field(..., description="Category: 金属/能源化工/农产品/金融期货")
    underlying_instrument: str | None = Field(None, description="Current leading specific contract code")
    contract_size: Decimal | None = None
    price_unit: str | None = None
    quote_unit: str | None = None
    is_main: bool = True
    list_date: date | None = None
    delist_date: date | None = None
    last_seen_at: datetime | None = None


class FuturesContractListResponse(BaseModel):
    """Paginated futures contract list response."""

    items: list[FuturesContractOut]
    total: int
    page: int = 1
    page_size: int = 200


# ---------------------------------------------------------------------------
# Daily bars
# ---------------------------------------------------------------------------


class FuturesDailyBarOut(BaseModel):
    """A single daily OHLCV row for a futures contract."""

    code: str
    trade_date: date
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    settle: Decimal | None = None
    pre_settle: Decimal | None = None
    volume: int | None = None
    open_interest: int | None = None
    turnover: Decimal | None = None
    warehouse_receipts: int | None = None

    # Derived: percentage change from pre_settle -> settle
    settle_change_pct: float | None = None
    # Derived: percentage change from pre_close -> close
    change_pct: float | None = None


class FuturesDailyBarListResponse(BaseModel):
    """Response wrapper for daily bars."""

    items: list[FuturesDailyBarOut]
    count: int
    code: str | None = None


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class FuturesDashboardSection(BaseModel):
    """Latest-day data for all contracts in one product group."""

    product: str
    product_label: str | None = None
    items: list[FuturesDailyBarOut]
    best_performer: FuturesDailyBarOut | None = None
    worst_performer: FuturesDailyBarOut | None = None
    count: int


class FuturesDashboardResponse(BaseModel):
    """Dashboard data grouped by product category."""

    sections: list[FuturesDashboardSection]
    trade_date: date | None = None
    total_contracts: int


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------


class FuturesLeaderboardRow(BaseModel):
    """A single row on the leaderboard."""

    code: str
    name: str
    exchange: str
    product: str
    close: Decimal | None = None
    settle: Decimal | None = None
    pre_settle: Decimal | None = None
    change_pct: float | None = None
    volume: int | None = None
    open_interest: int | None = None
    turnover: Decimal | None = None


class FuturesLeaderboardResponse(BaseModel):
    """Sorted leaderboard (gainers / losers)."""

    items: list[FuturesLeaderboardRow]
    direction: str = Field("gainers", description="gainers or losers")
    exchange: str | None = None
    trade_date: date | None = None


# ---------------------------------------------------------------------------
# Service-level filters
# ---------------------------------------------------------------------------


class FuturesFilterParams(BaseModel):
    """Internal filter params for the contract list endpoint."""

    exchange: str | None = None
    product: str | None = None
    is_main: bool | None = True
    search: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=200, ge=1, le=500)
