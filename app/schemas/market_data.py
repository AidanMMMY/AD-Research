from datetime import date

from pydantic import BaseModel


class DailyBarResponse(BaseModel):
    trade_date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int | None = None
    amount: float | None = None
    change_pct: float | None = None
    turnover_rate: float | None = None
    # 前复权相关字段（仅当 adjusted=True 时由 repository 填充）。
    # adj_factor 是该日相对最新参考点的复权因子；
    # adj_close = close * adj_factor，是连续可比的前复权收盘价。
    adj_factor: float | None = None
    adj_close: float | None = None


class MarketDataHistoryResponse(BaseModel):
    etf_code: str
    etf_name: str | None = None
    items: list[DailyBarResponse]


class SnapshotItem(BaseModel):
    etf_code: str
    etf_name: str | None = None
    close: float | None = None
    change_pct: float | None = None
    volume: int | None = None
    amount: float | None = None


class MarketSnapshotResponse(BaseModel):
    items: list[SnapshotItem]
    count: int
