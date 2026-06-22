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
