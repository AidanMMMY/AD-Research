"""Signal Pydantic schemas."""

from datetime import date

from pydantic import BaseModel


class SignalItem(BaseModel):
    """Signal item."""

    id: int
    strategy_id: int
    etf_code: str
    trade_date: str | None = None
    signal_type: str
    strength: int | None = None
    created_at: str | None = None


class SignalListResponse(BaseModel):
    """Signal list response."""

    items: list[SignalItem]


class SignalGenerateRequest(BaseModel):
    """Signal generation request."""

    strategy_id: int
    etf_code: str
    trade_date: date | None = None


class SignalGenerateResponse(BaseModel):
    """Signal generation response."""

    signals: list[SignalItem]
