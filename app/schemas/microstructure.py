"""A-share micro-structure data Pydantic schemas.

Used by the API layer to serialize ORM rows for the four micro-structure
data classes (龙虎榜 / 沪深港通 / 融资融券 / 限售解禁).
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 龙虎榜 (LHB)
# ---------------------------------------------------------------------------


class LhbRecordBase(BaseModel):
    """Common LHB fields exposed in list / detail responses."""

    trade_date: date
    ts_code: str
    name: str
    close: float | None = None
    pct_change: float | None = None
    turnover_rate: float | None = None
    amount: float | None = None

    lhb_buy_amount: float | None = None
    lhb_sell_amount: float | None = None
    lhb_net_amount: float | None = None

    total_buy: float | None = None
    total_sell: float | None = None
    total_net: float | None = None
    net_buy_amt: float | None = None

    buy_seat_count: int | None = None
    sell_seat_count: int | None = None
    reason: str


class LhbRecordOut(LhbRecordBase):
    """LHB record as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    created_at: datetime | None = None


class LhbRecordListResponse(BaseModel):
    """Paginated LHB list response."""

    items: list[LhbRecordOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# 沪深港通 (HSGT)
# ---------------------------------------------------------------------------


class HsgtFlowBase(BaseModel):
    """Common HSGT flow fields."""

    trade_date: date
    type: str = Field(..., description="资金流向类型: 北向 / 沪股通 / 深股通 / 南向")
    buy_amount: float | None = None
    sell_amount: float | None = None
    net_amount: float | None = None
    balance: float | None = None


class HsgtFlowOut(HsgtFlowBase):
    """HSGT flow record as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    created_at: datetime | None = None


class HsgtFlowListResponse(BaseModel):
    """HSGT flow list response (no pagination — short window)."""

    items: list[HsgtFlowOut]
    total: int


# ---------------------------------------------------------------------------
# 融资融券 (Margin)
# ---------------------------------------------------------------------------


class MarginBalanceBase(BaseModel):
    """Common margin balance fields."""

    trade_date: date
    ts_code: str
    name: str
    financing_balance: float | None = None
    financing_buy: float | None = None
    securities_balance: float | None = None
    securities_sell: float | None = None
    exchange: str = Field(..., description="交易所: SSE / SZSE")


class MarginBalanceOut(MarginBalanceBase):
    """Margin balance record as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    created_at: datetime | None = None


class MarginBalanceListResponse(BaseModel):
    """Paginated margin balance list response."""

    items: list[MarginBalanceOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# 限售解禁 (Restricted Release)
# ---------------------------------------------------------------------------


class RestrictedReleaseBase(BaseModel):
    """Common restricted-release fields."""

    ts_code: str
    name: str
    restricted_date: date
    restricted_type: str = ""
    restricted_number: float | None = None
    restricted_amount: float | None = None
    lift_ratio: float | None = None


class RestrictedReleaseOut(RestrictedReleaseBase):
    """Restricted release record as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    created_at: datetime | None = None


class RestrictedReleaseListResponse(BaseModel):
    """Paginated restricted-release list response."""

    items: list[RestrictedReleaseOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Summary (首页用)
# ---------------------------------------------------------------------------


class MicrostructureSummaryResponse(BaseModel):
    """Latest-day micro-structure summary for the dashboard.

    Each section is best-effort: a missing section means no fresh data
    was available for that data class on the latest trade date.
    """

    as_of: date | None = Field(
        None, description="汇总基准日 (四个分类中最近一个有数据的日期)"
    )
    lhb: dict[str, Any] = Field(
        default_factory=dict,
        description="龙虎榜: { trade_date, count, top_buyers, top_sellers }",
    )
    hsgt: dict[str, Any] = Field(
        default_factory=dict,
        description="北上资金: { trade_date, north_net, sh_net, sz_net }",
    )
    margin: dict[str, Any] = Field(
        default_factory=dict,
        description="融资融券: { trade_date, total_financing_balance, total_securities_balance }",
    )
    release: dict[str, Any] = Field(
        default_factory=dict,
        description="限售解禁: { upcoming_30d_count, upcoming_30d_amount }",
    )
