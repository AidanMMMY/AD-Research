"""A-Share Individual Stock Financial Statements ETL Pipeline.

Fetches quarterly income statements and balance sheets from Tushare
income_vip and balancesheet_vip endpoints, upserting into
``stock_income`` and ``stock_balance_sheet``.

Scheduled weekly (Monday 02:00 Beijing time) — financial statements
change infrequently (quarterly reporting cycles).

Uses per-stock API calls with rate limiting. For ~5000 A-share stocks
this processes a rotating batch of 500 stocks per run, achieving full
coverage in ~10 weeks (vs ~100 weeks with the previous batch size of 50).

Point budget (Tushare free tier, 5000 pts/day):
  500 stocks × (income_vip ~5 pts + balancesheet_vip ~5 pts) ≈ 5000 pts
"""

import logging
import time
from datetime import date

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.data.pipelines.base import ETLPipeline, ETLResult
from app.data.providers.tushare_provider import TushareProvider
from app.models.etf import ETFInfo, StockBalanceSheet, StockIncome

logger = logging.getLogger(__name__)

# Process a rotating subset per run to stay within rate limits.
# Tushare free tier: ~5000 points/day.
# income_vip:   ~5 points/call × 500 stocks = 2500 points/run
# balancesheet_vip: ~5 points/call × 500 stocks = 2500 points/run
# Total: ~5000 points/run — stays within daily budget
_BATCH_SIZE = 500


class AStockFinancialsPipeline(ETLPipeline):
    """Pipeline that fetches quarterly financial statements for A-share stocks.

    Processes a rotating batch of stocks each weekly run. The rotation is
    achieved by fetching stocks ordered by code and selecting the next batch
    based on the week of year.
    """

    job_name = "a_stock_financials"

    def __init__(self, db: Session) -> None:
        provider = TushareProvider()
        super().__init__(provider=provider, db=db)

    def run(self) -> ETLResult:
        """Override base run() — financial data doesn't go through OHLCV validator."""
        result = ETLResult()
        self._create_log()

        try:
            income_count, bs_count = self._run_impl()
            result.records = income_count + bs_count
            result.success = True
            self._update_log(status="success", records=result.records)
            logger.info(
                "AStockFinancialsPipeline: Income=%d, BalanceSheet=%d",
                income_count, bs_count,
            )

        except Exception as exc:
            error_msg = str(exc)
            result.success = False
            result.error = error_msg
            self._update_log(status="failed", error=error_msg)
            logger.error("AStockFinancialsPipeline failed: %s", error_msg)

        return result

    def _run_impl(self) -> tuple[int, int]:
        """Core implementation: fetch and upsert financial statements.

        Returns (income_records, balance_sheet_records).
        """

        # 1. Get active A-share stocks, sorted by code for rotation
        stocks = (
            self.db.query(ETFInfo)
            .filter(ETFInfo.market == "A股")
            .filter(ETFInfo.instrument_type == "STOCK")
            .filter(ETFInfo.status == "active")
            .order_by(ETFInfo.code)
            .all()
        )

        if not stocks:
            logger.warning("AStockFinancialsPipeline: No active A-share stocks")
            return 0, 0

        # 2. Rotating batch: pick stocks based on week of year
        week_of_year = int(time.strftime("%W"))
        start_idx = (week_of_year * _BATCH_SIZE) % len(stocks)
        batch = stocks[start_idx : start_idx + _BATCH_SIZE]
        codes = [s.code for s in batch]

        logger.info(
            "AStockFinancialsPipeline: Week %d, processing %d stocks (offset=%d/%d)",
            week_of_year, len(codes), start_idx, len(stocks),
        )

        # 3. Fetch and upsert
        provider = TushareProvider()
        income_records = 0
        bs_records = 0

        for code in codes:
            # Income statement
            try:
                df_income = provider.fetch_income_vip(code, limit=4)
                if df_income is not None and not df_income.empty:
                    inc = self._upsert_income(df_income)
                    income_records += inc
            except Exception as exc:
                logger.warning(
                    "AStockFinancialsPipeline: income_vip(%s) failed: %s", code, exc
                )

            # Balance sheet
            try:
                df_bs = provider.fetch_balancesheet_vip(code, limit=4)
                if df_bs is not None and not df_bs.empty:
                    bs = self._upsert_balance_sheet(df_bs)
                    bs_records += bs
            except Exception as exc:
                logger.warning(
                    "AStockFinancialsPipeline: balancesheet_vip(%s) failed: %s", code, exc
                )

        return income_records, bs_records

    def _upsert_income(self, df: pd.DataFrame) -> int:
        """Upsert income statement records."""

        field_map: list[tuple[str, str]] = [
            ("etf_code", "stock_code"),
            ("end_date", "end_date"),
            ("report_type", "report_type"),
            ("ann_date", "ann_date"),
            ("total_revenue", "total_revenue"),
            ("revenue_yoy", "rev_yoy"),
            ("operate_profit", "operate_profit"),
            ("total_profit", "total_profit"),
            ("n_income", "n_income"),
            ("n_income_yoy", "n_income_yoy"),
            ("basic_eps", "basic_eps"),
            ("grossprofit_margin", "grossprofit_margin"),
            ("netprofit_margin", "netprofit_margin"),
            ("roe", "roe"),
            ("roe_dt", "roe_dt"),
            ("n_operate_cashflow", "n_operate_cashflow"),
        ]

        records = []
        for _, row in df.iterrows():
            record = {}
            for src_col, dst_col in field_map:
                val = row.get(src_col)
                if val is not None and not (isinstance(val, float) and pd.isna(val)):
                    record[dst_col] = val
            if record.get("stock_code") and record.get("end_date"):
                records.append(record)

        if not records:
            return 0

        stmt = (
            insert(StockIncome)
            .values(records)
            .on_conflict_do_update(
                index_elements=["stock_code", "end_date", "report_type"],
                set_={
                    "ann_date": insert(StockIncome).excluded.ann_date,
                    "total_revenue": insert(StockIncome).excluded.total_revenue,
                    "revenue_yoy": insert(StockIncome).excluded.revenue_yoy,
                    "operate_profit": insert(StockIncome).excluded.operate_profit,
                    "total_profit": insert(StockIncome).excluded.total_profit,
                    "n_income": insert(StockIncome).excluded.n_income,
                    "n_income_yoy": insert(StockIncome).excluded.n_income_yoy,
                    "basic_eps": insert(StockIncome).excluded.basic_eps,
                    "grossprofit_margin": insert(StockIncome).excluded.grossprofit_margin,
                    "netprofit_margin": insert(StockIncome).excluded.netprofit_margin,
                    "roe": insert(StockIncome).excluded.roe,
                    "roe_dt": insert(StockIncome).excluded.roe_dt,
                    "n_operate_cashflow": insert(StockIncome).excluded.n_operate_cashflow,
                },
            )
        )

        self.db.execute(stmt)
        self.db.commit()
        return len(records)

    def _upsert_balance_sheet(self, df: pd.DataFrame) -> int:
        """Upsert balance sheet records."""

        field_map: list[tuple[str, str]] = [
            ("etf_code", "stock_code"),
            ("end_date", "end_date"),
            ("report_type", "report_type"),
            ("ann_date", "ann_date"),
            ("total_assets", "total_assets"),
            ("total_liab", "total_liab"),
            ("total_hldr_eqy_exc_min_int", "total_hldr_eqy_exc_min_int"),
            ("total_cur_assets", "total_cur_assets"),
            ("total_cur_liab", "total_cur_liab"),
            ("current_ratio", "current_ratio"),
            ("debt_to_assets", "debt_to_assets"),
        ]

        records = []
        for _, row in df.iterrows():
            record = {}
            for src_col, dst_col in field_map:
                val = row.get(src_col)
                if val is not None and not (isinstance(val, float) and pd.isna(val)):
                    record[dst_col] = val
            if record.get("stock_code") and record.get("end_date"):
                records.append(record)

        if not records:
            return 0

        stmt = (
            insert(StockBalanceSheet)
            .values(records)
            .on_conflict_do_update(
                index_elements=["stock_code", "end_date", "report_type"],
                set_={
                    "ann_date": insert(StockBalanceSheet).excluded.ann_date,
                    "total_assets": insert(StockBalanceSheet).excluded.total_assets,
                    "total_liab": insert(StockBalanceSheet).excluded.total_liab,
                    "total_hldr_eqy_exc_min_int": insert(StockBalanceSheet).excluded.total_hldr_eqy_exc_min_int,
                    "total_cur_assets": insert(StockBalanceSheet).excluded.total_cur_assets,
                    "total_cur_liab": insert(StockBalanceSheet).excluded.total_cur_liab,
                    "current_ratio": insert(StockBalanceSheet).excluded.current_ratio,
                    "debt_to_assets": insert(StockBalanceSheet).excluded.debt_to_assets,
                },
            )
        )

        self.db.execute(stmt)
        self.db.commit()
        return len(records)

    def extract(self) -> pd.DataFrame:
        """Not used — custom run() handles extraction."""
        return pd.DataFrame()

    def load(self, data: pd.DataFrame) -> int:
        """Not used — _run_impl() handles loading."""
        return 0
