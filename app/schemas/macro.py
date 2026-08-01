"""Pydantic schemas for the macro indicators API."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MacroIndicatorItem(BaseModel):
    """One row of macro-indicator metadata (used in list / latest)."""

    model_config = ConfigDict(from_attributes=True)

    code: str = Field(..., description="Stable indicator code (e.g. us_cpi)")
    region: str = Field(..., description="Region code: us, cn, global, ...")
    name_zh: str = Field(..., description="Chinese display name")
    name_en: str | None = Field(None, description="English display name")
    unit: str = Field("", description="Display unit")
    source: str = Field(..., description="Data source tag: fred, nbs, ...")


class MacroIndicatorLatestItem(MacroIndicatorItem):
    """Indicator metadata plus the most recent observation."""

    period: date | None = Field(None, description="Latest observation date")
    value: float | None = Field(None, description="Latest observation value")
    fetched_at: datetime | None = Field(None, description="When this row was last upserted")


class MacroIndicatorPoint(BaseModel):
    """A single observation point on a chart."""

    period: date
    value: float


class MacroIndicatorSeries(BaseModel):
    """Time-series response for one indicator."""

    code: str
    region: str
    name_zh: str
    name_en: str | None = None
    unit: str = ""
    source: str = ""
    points: list[MacroIndicatorPoint]


class MacroRefreshResponse(BaseModel):
    """Response shape for the manual refresh endpoint."""

    written: int = Field(..., description="Number of rows upserted")
    series_count: int = Field(..., description="Number of series attempted")
    failed: list[str] = Field(
        default_factory=list,
        description="Series IDs that failed to refresh",
    )
    started_at: datetime
    finished_at: datetime


class MacroIndicatorOut(BaseModel):
    """One macro indicator observation row (list endpoint)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    region: str
    name_zh: str
    name_en: str | None = None
    unit: str | None = None
    period: date
    value: float
    source: str
    fetched_at: datetime | None = None


class MacroIndicatorListResponse(BaseModel):
    """Paginated list of macro indicator observations."""

    items: list[MacroIndicatorOut]
    total: int
    page: int
    page_size: int


class MacroCodeInfo(BaseModel):
    """Distinct (code, region, name_zh, unit) tuple used for the codes dropdown."""

    code: str
    region: str
    name_zh: str
    name_en: str | None = None
    unit: str | None = None
    source: str
    latest_period: date | None = None
    latest_value: float | None = None


class MacroCodeListResponse(BaseModel):
    """Distinct indicator codes registered in the macro_indicator table."""

    items: list[MacroCodeInfo] = Field(default_factory=list)


class MacroLatestItem(BaseModel):
    """Latest snapshot for one (code, region) pair."""

    code: str
    region: str
    name_zh: str
    name_en: str | None = None
    unit: str | None = None
    source: str
    period: date
    value: float
    prev_value: float | None = None
    change_pct: float | None = None
    fetched_at: datetime | None = None
    freshness_hint: str | None = Field(
        None,
        description=(
            "Localized hint about why this row may be older than today "
            "(e.g. FRED weekly FX lag). None if the row is current."
        ),
    )


class MacroLatestResponse(BaseModel):
    """Latest snapshot across all codes (one row per code+region)."""

    items: list[MacroLatestItem] = Field(default_factory=list)
    region: str | None = None


# ---------------------------------------------------------------------------
# 全球速览指数详情页（Batch B API 契约）
# ---------------------------------------------------------------------------


class MacroOhlcBar(BaseModel):
    """一根日线 OHLCV K 线（open/high/low/volume 可为空）."""

    date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float
    volume: int | None = None


class MacroIndicatorLatest(BaseModel):
    """详情页头部卡片的最新值与前值/涨跌."""

    period: date
    value: float
    prev_value: float | None = None
    change_pct: float | None = None
    change_abs: float | None = None


class MacroIndicatorStats(BaseModel):
    """详情页统计块：序列范围 + 52 周高低."""

    first_period: date | None = None
    last_period: date | None = None
    count: int = 0
    high_52w: float | None = None
    low_52w: float | None = None


class MacroIndicatorDetail(BaseModel):
    """详情页聚合响应.

    ``has_ohlc=True`` 时 ``ohlc`` 非空、``points`` 可为空数组；
    ``has_ohlc=False`` 时 ``ohlc=None``、``points`` 来自
    macro_indicator 折线序列（FRED 代码走这里）。
    """

    code: str
    region: str
    name_zh: str
    name_en: str | None = None
    unit: str = ""
    source: str = ""
    category: Literal["rate", "fx", "commodity", "index", "vol"]
    has_ohlc: bool
    latest: MacroIndicatorLatest | None = None
    stats: MacroIndicatorStats
    ohlc: list[MacroOhlcBar] | None = None
    points: list[MacroIndicatorPoint] = Field(default_factory=list)