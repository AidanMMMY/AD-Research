from datetime import date

from pydantic import BaseModel, ConfigDict


class StockFundamentalResponse(BaseModel):
    """A-share stock valuation & market data (latest record)."""

    model_config = ConfigDict(from_attributes=True)

    stock_code: str
    trade_date: date
    pe_ttm: float | None = None
    pb: float | None = None
    total_mv: float | None = None  # 万元 CNY
    circ_mv: float | None = None   # 万元 CNY
    turnover_rate_f: float | None = None
    volume_ratio: float | None = None
    total_share: float | None = None  # 万股
    float_share: float | None = None  # 万股

    # Enriched from stock_income (latest quarter)
    eps: float | None = None
    roe: float | None = None
    revenue_yoy: float | None = None
    grossprofit_margin: float | None = None
    netprofit_margin: float | None = None
