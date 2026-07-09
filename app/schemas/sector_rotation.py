"""Sector rotation Pydantic schemas.

The contract is intentionally **backward-compatible at the response-shape
level** — endpoint URLs, query params and top-level keys stay the same —
but the semantics of ``sector`` (was: ETF 基金类型 like "股票型"; now:
GICS industry sector like "Information Technology") have changed.

See ``app/services/sector_rotation_service.py`` for the rationale.
"""


from typing import Literal

from pydantic import BaseModel, Field


class SectorScope(BaseModel):
    """Universe scope of the analysis."""

    market: Literal["A股"] = Field(..., description="Trading market scope")
    instrument_types: list[Literal["ETF", "STOCK"]] = Field(
        ..., description="Instrument types included"
    )
    classification: Literal["GICS", "SW"] = Field(
        ...,
        description="Industry classification system: GICS (default, global) "
        "or SW (申万2021一级, A-share only)",
    )


class SectorPerformance(BaseModel):
    """Sector performance metrics (per GICS sector)."""

    sector: str = Field(..., description="GICS sector name (level-1)")
    count: int = Field(..., description="Total instruments in the sector")
    stock_count: int = Field(..., description="Individual stock count")
    etf_count: int = Field(..., description="ETF count")
    return_1w: float = Field(..., description="1-week average return (%)")
    return_1m: float = Field(..., description="1-month average return (%)")
    return_3m: float = Field(..., description="3-month average return (%)")
    return_6m: float = Field(..., description="6-month average return (%)")
    return_1y: float = Field(..., description="1-year average return (%)")
    sharpe_1y: float = Field(..., description="1-year Sharpe (average)")
    volatility_20d: float = Field(..., description="20-day volatility (average)")
    rsi14: float = Field(..., description="RSI14 (average)")
    amount_total: float = Field(..., description="Aggregate turnover (元)")
    relative_strength_1w: float = Field(
        ..., description="Relative strength vs market avg (1w)"
    )
    relative_strength_1m: float = Field(
        ..., description="Relative strength vs market avg (1m)"
    )
    relative_strength_3m: float = Field(
        ..., description="Relative strength vs market avg (3m)"
    )
    momentum_rank: int = Field(..., description="Rank by 1m return (1=best)")


class RotationSignal(BaseModel):
    """Sector rotation signal — sector moved up/down ≥3 positions in rank."""

    sector: str
    type: str  # "up" or "down"
    message: str
    current_rank: int
    previous_rank: int
    rank_change: int = Field(
        ..., description="Positive = moved up; negative = moved down"
    )


class MarketAverage(BaseModel):
    """Market-average metrics across all sectors in scope."""

    return_1w: float
    return_1m: float
    return_3m: float
    return_6m: float
    return_1y: float
    sharpe_1y: float


class SectorRotationResponse(BaseModel):
    """Sector rotation analysis response."""

    trade_date: str
    scope: SectorScope
    sectors: list[SectorPerformance]
    market_avg: MarketAverage | None
    rotation_signals: list[RotationSignal]


class SectorListItem(BaseModel):
    """Sector list item — distinct sector with composition counts."""

    sector: str
    count: int
    stock_count: int
    etf_count: int


class SectorListResponse(BaseModel):
    """Sector list response."""

    items: list[SectorListItem]


# ---------------------------------------------------------------------------
# Constituents view (added 2026-07-09)
# ---------------------------------------------------------------------------


class SectorConstituent(BaseModel):
    """Single instrument inside a sector, ranked by weight (market cap for
    STOCK, fund size for ETF).

    The ``weight`` field is intentionally heterogeneous — the
    ``weight_unit`` and ``weight_label`` fields tell the UI how to render
    it. Mixing STOCKs (市值 in 元) and ETFs (规模 in 元) in one table is
    fine for drill-down purposes: the user is looking at the *composition*
    of the sector, not a weighted sum.
    """

    code: str
    name: str
    instrument_type: Literal["ETF", "STOCK"]
    # Sector classification that resolved (might be `etf_info.sector` or
    # the keyword-inferred fallback for ETFs). Echoed so the client can
    # render a tag without re-running the heuristic.
    resolved_sector: str
    # Weight metric. None when the upstream data is missing (e.g. stock
    # not yet in `stock_fundamental`).
    weight: float | None = Field(
        None, description="Weight value (market cap or fund size in CNY 元)"
    )
    weight_unit: Literal["元"] = Field(
        "元", description="Currency unit for weight (always CNY 元)"
    )
    weight_label: Literal["市值", "规模"] = Field(
        ...,
        description="Label for the weight column: '市值' for STOCK, '规模' for ETF",
    )

    # Period returns — same shape as SectorPerformance so the UI can
    # reuse the ReturnTag component.
    return_1w: float | None = None
    return_1m: float | None = None
    return_3m: float | None = None
    return_6m: float | None = None
    return_1y: float | None = None

    # Liquidity / quality (optional — surfaced when present)
    sharpe_1y: float | None = None
    rsi14: float | None = None
    amount_total: float | None = None


class SectorConstituentsResponse(BaseModel):
    """Top-N constituents for a single GICS sector.

    Returned by ``GET /sector-rotation/sectors/{sector}/constituents``.
    """

    sector: str = Field(..., description="GICS sector name (matches path param)")
    trade_date: str | None = Field(
        None, description="Analysis date (ISO); null when no indicators are seeded"
    )
    count: int = Field(..., description="Number of constituents returned")
    total_in_sector: int = Field(
        ...,
        description=(
            "Total instruments in the sector (after sector-resolution). "
            "Useful for the UI to render 'showing top N of M'."
        ),
    )
    items: list[SectorConstituent]