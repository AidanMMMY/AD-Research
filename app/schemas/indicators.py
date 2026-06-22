from datetime import date

from pydantic import BaseModel


class IndicatorResponse(BaseModel):
    etf_code: str
    trade_date: date
    # 移动平均
    ma5: float | None = None
    ma10: float | None = None
    ma20: float | None = None
    ma60: float | None = None
    # 动量
    rsi14: float | None = None
    macd_dif: float | None = None
    macd_dea: float | None = None
    macd_hist: float | None = None
    # 风险
    volatility_20d: float | None = None
    volatility_60d: float | None = None
    max_drawdown_1y: float | None = None
    sharpe_1y: float | None = None
    # 收益
    return_1w: float | None = None
    return_1m: float | None = None
    return_3m: float | None = None
    return_6m: float | None = None
    return_1y: float | None = None
    # 其他
    atr14: float | None = None
    bb_upper: float | None = None
    bb_lower: float | None = None


class IndicatorBatchResponse(BaseModel):
    items: list[IndicatorResponse]
    count: int
