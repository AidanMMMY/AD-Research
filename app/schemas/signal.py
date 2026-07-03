"""Signal Pydantic schemas."""

from datetime import date
from typing import Any

from pydantic import BaseModel


class SignalItem(BaseModel):
    """Signal item."""

    id: int
    strategy_id: int
    strategy_name: str | None = None
    strategy_type: str | None = None
    etf_code: str
    etf_name: str | None = None
    name_zh: str | None = None
    trade_date: str | None = None
    signal_type: str
    strength: int | None = None
    extra_data: dict[str, Any] | None = None
    created_at: str | None = None


class SignalListResponse(BaseModel):
    """Signal list response."""

    items: list[SignalItem]


class SignalGenerateRequest(BaseModel):
    """Signal generation request."""

    strategy_id: int
    etf_code: str
    trade_date: date | None = None


class SignalBulkGenerateRequest(BaseModel):
    """Bulk signal generation request for a universe of instruments."""

    strategy_id: int
    etf_codes: list[str]
    trade_date: date | None = None


class SignalGenerateResponse(BaseModel):
    """Signal generation response."""

    signals: list[SignalItem]
