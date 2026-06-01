"""Signal Pydantic schemas."""

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class SignalItem(BaseModel):
    """Signal item."""

    id: int
    strategy_id: int
    etf_code: str
    trade_date: Optional[str] = None
    signal_type: str
    strength: Optional[int] = None
    created_at: Optional[str] = None


class SignalListResponse(BaseModel):
    """Signal list response."""

    items: List[SignalItem]


class SignalGenerateRequest(BaseModel):
    """Signal generation request."""

    strategy_id: int
    etf_code: str
    trade_date: Optional[date] = None


class SignalGenerateResponse(BaseModel):
    """Signal generation response."""

    signals: List[SignalItem]
