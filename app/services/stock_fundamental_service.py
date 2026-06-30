"""Service layer for A-share individual stock fundamental data.

Provides read-only queries against stock_fundamental and stock_income tables.
"""

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.etf import StockBalanceSheet, StockFundamental, StockIncome


class StockFundamentalService:
    """Queries A-share stock valuation, market data and income statements."""

    def __init__(self, db: Session):
        self.db = db

    def get_latest(self, stock_code: str) -> dict | None:
        """Return the latest fundamental + income snapshot for a stock.

        Returns a flat dict with: pe_ttm, pb, total_mv, circ_mv, turnover_rate_f,
        volume_ratio, total_share, float_share, eps, roe, revenue_yoy,
        grossprofit_margin, netprofit_margin.

        Returns None if the stock is not found in stock_fundamental.
        """
        # Latest fundamental
        fund = (
            self.db.query(StockFundamental)
            .filter(StockFundamental.stock_code == stock_code)
            .order_by(StockFundamental.trade_date.desc())
            .limit(1)
            .first()
        )
        if fund is None:
            return None

        result = {
            "stock_code": fund.stock_code,
            "trade_date": fund.trade_date,
            "pe_ttm": float(fund.pe_ttm) if fund.pe_ttm is not None else None,
            "pb": float(fund.pb) if fund.pb is not None else None,
            "total_mv": float(fund.total_mv) if fund.total_mv is not None else None,
            "circ_mv": float(fund.circ_mv) if fund.circ_mv is not None else None,
            "turnover_rate_f": float(fund.turnover_rate_f) if fund.turnover_rate_f is not None else None,
            "volume_ratio": float(fund.volume_ratio) if fund.volume_ratio is not None else None,
            "total_share": float(fund.total_share) if fund.total_share is not None else None,
            "float_share": float(fund.float_share) if fund.float_share is not None else None,
        }

        # Latest income statement
        income = (
            self.db.query(StockIncome)
            .filter(StockIncome.stock_code == stock_code)
            .order_by(StockIncome.end_date.desc())
            .limit(1)
            .first()
        )
        if income is not None:
            result["eps"] = float(income.basic_eps) if income.basic_eps is not None else None
            result["roe"] = float(income.roe) if income.roe is not None else None
            result["revenue_yoy"] = float(income.revenue_yoy) if income.revenue_yoy is not None else None
            result["grossprofit_margin"] = float(income.grossprofit_margin) if income.grossprofit_margin is not None else None
            result["netprofit_margin"] = float(income.netprofit_margin) if income.netprofit_margin is not None else None

        return result

    def get_financials_history(
        self, stock_code: str, limit: int = 20
    ) -> dict:
        """Return historical income statements and balance sheets for a stock.

        Returns a dict with ``income`` and ``balance_sheet`` arrays, each
        ordered by ``end_date`` descending (most recent quarter first).
        """

        def _to_float(value) -> float | None:
            return float(value) if value is not None else None

        income_rows = (
            self.db.query(StockIncome)
            .filter(StockIncome.stock_code == stock_code)
            .order_by(desc(StockIncome.end_date))
            .limit(limit)
            .all()
        )

        balance_rows = (
            self.db.query(StockBalanceSheet)
            .filter(StockBalanceSheet.stock_code == stock_code)
            .order_by(desc(StockBalanceSheet.end_date))
            .limit(limit)
            .all()
        )

        income = [
            {
                "end_date": row.end_date,
                "report_type": row.report_type,
                "ann_date": row.ann_date,
                "total_revenue": _to_float(row.total_revenue),
                "revenue_yoy": _to_float(row.revenue_yoy),
                "operate_profit": _to_float(row.operate_profit),
                "total_profit": _to_float(row.total_profit),
                "n_income": _to_float(row.n_income),
                "n_income_yoy": _to_float(row.n_income_yoy),
                "basic_eps": _to_float(row.basic_eps),
                "grossprofit_margin": _to_float(row.grossprofit_margin),
                "netprofit_margin": _to_float(row.netprofit_margin),
                "roe": _to_float(row.roe),
                "roe_dt": _to_float(row.roe_dt),
                "n_operate_cashflow": _to_float(row.n_operate_cashflow),
            }
            for row in income_rows
        ]

        balance_sheet = [
            {
                "end_date": row.end_date,
                "report_type": row.report_type,
                "ann_date": row.ann_date,
                "total_assets": _to_float(row.total_assets),
                "total_liab": _to_float(row.total_liab),
                "total_hldr_eqy_exc_min_int": _to_float(row.total_hldr_eqy_exc_min_int),
                "total_cur_assets": _to_float(row.total_cur_assets),
                "total_cur_liab": _to_float(row.total_cur_liab),
                "current_ratio": _to_float(row.current_ratio),
                "debt_to_assets": _to_float(row.debt_to_assets),
            }
            for row in balance_rows
        ]

        return {
            "stock_code": stock_code,
            "income": income,
            "balance_sheet": balance_sheet,
        }
