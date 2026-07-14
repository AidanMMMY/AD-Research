"""免费资金流 Pydantic Schemas (方案 C API 契约)。

前端 agent 直接消费这些 schema；JSON 字段名与数据库 ORM 字段保持一致
（snake_case），与 API 契约注释中的 TypeScript 字段顺序一致。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 1. 个股资金流
# ---------------------------------------------------------------------------


class IndividualFundFlowBase(BaseModel):
    """个股资金流公共字段。"""

    ts_code: str
    trade_date: date
    main_net_inflow: float | None = None
    main_net_pct: float | None = None
    super_large_net: float | None = None
    super_large_pct: float | None = None
    large_net: float | None = None
    large_pct: float | None = None
    medium_net: float | None = None
    medium_pct: float | None = None
    small_net: float | None = None
    small_pct: float | None = None


class IndividualFundFlowOut(IndividualFundFlowBase):
    """API 返回的个股资金流记录。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str = "akshare"
    fetched_at: datetime | None = None


class IndividualFundFlowListResponse(BaseModel):
    """个股资金流列表响应 (分页)。"""

    items: list[IndividualFundFlowOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# 2. 板块资金流
# ---------------------------------------------------------------------------


class SectorFundFlowBase(BaseModel):
    """板块资金流公共字段。"""

    sector_name: str
    sector_type: str = Field(..., description="板块类型: 行业 / 概念 / 地域")
    trade_date: date
    main_net_inflow: float | None = None
    main_net_pct: float | None = None
    super_large_net: float | None = None
    large_net: float | None = None
    leading_stock: str | None = None


class SectorFundFlowOut(SectorFundFlowBase):
    """API 返回的板块资金流记录。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    fetched_at: datetime | None = None


class SectorFundFlowListResponse(BaseModel):
    """板块资金流列表响应。"""

    items: list[SectorFundFlowOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# 3. ETF 资金流
# ---------------------------------------------------------------------------


class EtfFundFlowBase(BaseModel):
    """ETF 资金流公共字段。"""

    ts_code: str
    trade_date: date
    price: float | None = None
    net_value: float | None = None
    premium_rate: float | None = None
    shares_outstanding: float | None = None
    shares_change: float | None = None
    turnover: float | None = None
    inferred_net_inflow: float | None = None


class EtfFundFlowOut(EtfFundFlowBase):
    """API 返回的 ETF 资金流记录。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    fetched_at: datetime | None = None


class EtfFundFlowListResponse(BaseModel):
    """ETF 资金流列表响应。"""

    items: list[EtfFundFlowOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# 4. 综合资金信号
# ---------------------------------------------------------------------------


class FlowSignalBase(BaseModel):
    """综合资金信号公共字段。"""

    ts_code: str
    trade_date: date
    main_net_inflow: float | None = None
    margin_net_change: float | None = None
    lhb_net_buy: float | None = None
    shareholder_count_change: float | None = None
    ah_premium: float | None = None
    block_trade_net: float | None = None
    composite_score: float | None = None
    score_breakdown: dict[str, Any] | None = None


class FlowSignalOut(FlowSignalBase):
    """API 返回的综合资金信号记录。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    fetched_at: datetime | None = None


class FlowSignalListResponse(BaseModel):
    """综合资金信号列表响应。"""

    items: list[FlowSignalOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# 5. 大盘整体资金流 (ak.stock_market_fund_flow)
# ---------------------------------------------------------------------------


class MarketFundFlowOut(BaseModel):
    """大盘整体资金流 (ak.stock_market_fund_flow 一次返回两行)。"""

    trade_date: date = Field(..., description="交易日期 (akshare 上证/深证 同步)")
    sh_main_net_inflow: float | None = None
    sz_main_net_inflow: float | None = None
    sh_main_net_pct: float | None = None
    sz_main_net_pct: float | None = None


class MarketFundFlowListResponse(BaseModel):
    """大盘资金流多日响应。"""

    items: list[MarketFundFlowOut]
    total: int
