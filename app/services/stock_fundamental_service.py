"""Service layer for A-share individual stock fundamental data.

Provides read-only queries against stock_fundamental and stock_income tables.
"""

from sqlalchemy.orm import Session

from app.models.etf import StockFundamental, StockIncome


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
