from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ETFInfoBase(BaseModel):
    code: str
    name: str
    name_zh: str | None = None
    exchange: str | None = None
    market: str | None = None
    category: str | None = None
    sub_category: str | None = None
    manager: str | None = None
    currency: str = "CNY"
    is_qdii: bool = False
    underlying_index: str | None = None
    inception_date: date | None = None
    status: str = "active"


class ETFInfoResponse(ETFInfoBase):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    fund_manager: str | None = None
    fund_size: float | None = None
    instrument_type: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    country: str | None = None
    # A-share listing market (上海/深圳/北京) and board (主板/创业板/科创板/北交所).
    # Both fields are nullable; only populated for A-share instruments.
    listing_market: str | None = None
    board: str | None = None


class ETFListResponse(BaseModel):
    items: list[ETFInfoResponse]
    total: int
    page: int
    page_size: int


class ETFFilterParams(BaseModel):
    market: str | None = None
    category: str | None = None
    sub_category: str | None = None
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    manager: str | None = None
    underlying_index: str | None = None
    currency: str | None = None
    is_qdii: bool | None = None
    status: str | None = None
    instrument_type: str | None = None
    min_fund_size: float | None = None
    max_fund_size: float | None = None
    search: str | None = None
    listing_market: str | None = None
    board: str | None = None
    page: int = 1
    page_size: int = 50


class SparklineOut(BaseModel):
    """Recent N-day close price series for inline chart previews.

    Returned by ``GET /etfs/{code}/sparkline``. ``points`` and ``dates`` are
    ordered chronologically (oldest -> newest), so the frontend can render
    the series directly without reversing.
    """

    code: str
    days: int
    points: list[float]
    dates: list[str]  # ISO date strings (YYYY-MM-DD), same length as points


class ETFHoldingItem(BaseModel):
    """One row of an ETF's holdings snapshot.

    Both ``holdings_as_of_date`` (legacy column) and ``snapshot_date``
    (the new upsert identity) are surfaced. After the
    ``add_snapshot_date_to_etf_holding`` migration the two are equal
    for every populated row; ``holdings_as_of_date`` is kept in the
    response so existing front-end renders keep working.
    """

    etf_code: str
    holding_code: str
    holding_name: str | None = None
    weight: float | None = None
    shares: float | None = None
    market_value: float | None = None
    holdings_as_of_date: date | None = None
    snapshot_date: date | None = None


class ETFHoldingResponse(BaseModel):
    """Holdings response with the reporting-period echo.

    ``snapshot_date`` is the upsert identity used internally; the
    legacy ``holdings_as_of_date`` is preserved for backwards
    compatibility. When both are populated they should be equal.
    """

    holdings: list[ETFHoldingItem]
    holdings_as_of_date: date | None = None
    snapshot_date: date | None = None


class ETFHoldingSnapshotItem(BaseModel):
    """A single reporting-period snapshot descriptor.

    Returned by ``GET /etfs/{code}/holdings/snapshots`` so the frontend
    can list every available quarterly disclosure for an ETF.
    """

    holdings_as_of_date: date
    holding_count: int
    total_weight: float | None = None
    source: str | None = None


class ETFHoldingSnapshotListResponse(BaseModel):
    """Wrapper around the list of snapshot descriptors."""

    items: list[ETFHoldingSnapshotItem]


class ETFHoldingDiffEntry(BaseModel):
    """A single diff row between two reporting periods.

    ``status`` is one of:

    * ``unchanged`` — holding existed in both periods
    * ``added`` — only in ``to`` (new position)
    * ``removed`` — only in ``from`` (exited)
    * ``increased`` / ``decreased`` — in both, weight went up / down
    """

    holding_code: str
    holding_name: str | None = None
    from_weight: float | None = None
    to_weight: float | None = None
    weight_change: float | None = None
    from_shares: float | None = None
    to_shares: float | None = None
    shares_change: float | None = None
    status: str


class ETFHoldingDiffResponse(BaseModel):
    """Diff between two reporting periods for an ETF.

    Returns per-holding deltas plus aggregate counters the frontend
    can surface as KPIs (新增 / 减少 / 加权变化).
    """

    from_date: date | None = None
    to_date: date | None = None
    entries: list[ETFHoldingDiffEntry]
    added_count: int
    removed_count: int
    increased_count: int
    decreased_count: int
    unchanged_count: int
    total_weight_change: float | None = None
    from_total_weight: float | None = None
    to_total_weight: float | None = None
