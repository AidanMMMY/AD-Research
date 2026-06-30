"""Schemas for A-share individual stock financial statements."""

from datetime import date

from pydantic import BaseModel, ConfigDict


class StockIncomeItem(BaseModel):
    """One quarterly income statement record."""

    model_config = ConfigDict(from_attributes=True)

    end_date: date
    report_type: str
    ann_date: date | None = None
    total_revenue: float | None = None
    revenue_yoy: float | None = None
    operate_profit: float | None = None
    total_profit: float | None = None
    n_income: float | None = None
    n_income_yoy: float | None = None
    basic_eps: float | None = None
    grossprofit_margin: float | None = None
    netprofit_margin: float | None = None
    roe: float | None = None
    roe_dt: float | None = None
    n_operate_cashflow: float | None = None


class StockBalanceSheetItem(BaseModel):
    """One quarterly balance sheet record."""

    model_config = ConfigDict(from_attributes=True)

    end_date: date
    report_type: str
    ann_date: date | None = None
    total_assets: float | None = None
    total_liab: float | None = None
    total_hldr_eqy_exc_min_int: float | None = None
    total_cur_assets: float | None = None
    total_cur_liab: float | None = None
    current_ratio: float | None = None
    debt_to_assets: float | None = None


class StockFinancialsResponse(BaseModel):
    """Combined financial statement history for a stock."""

    stock_code: str
    income: list[StockIncomeItem]
    balance_sheet: list[StockBalanceSheetItem]
