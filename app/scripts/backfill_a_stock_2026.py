#!/usr/bin/env python3
"""Historical data backfill script for A-share individual stocks.

Fills missing daily bars, valuation data (PE/PB/market cap), and financial
statements for a specified date range. Designed to run in batches to stay
within Tushare free-tier limits (~5000 points/day).

Modes:
  bars          Daily OHLCV bars → etf_daily_bar      (1 API call/date)
  fundamental   PE/PB/market cap → stock_fundamental   (1 API call/date)
  financials    Income + balance → stock_income/_sheet  (2 API calls/stock)
  all           Run bars + fundamental sequentially (not financials)

Usage:
    # Backfill daily bars for Jan 2026 (~20 trading days, ~20 API calls)
    docker exec etf-backend python3 app/scripts/backfill_a_stock_2026.py \\
        --mode bars --start 20260102 --end 20260131

    # Backfill fundamentals for a month
    docker exec etf-backend python3 app/scripts/backfill_a_stock_2026.py \\
        --mode fundamental --start 20260301 --end 20260331

    # Dry-run to see what would be fetched (no DB writes)
    docker exec etf-backend python3 app/scripts/backfill_a_stock_2026.py \\
        --mode bars --start 20260601 --end 20260628 --dry-run

    # Backfill financials (per-stock, rotating batch of 500)
    docker exec etf-backend python3 app/scripts/backfill_a_stock_2026.py \\
        --mode financials --batch-offset 0

Point budget (Tushare free tier: 5000 pts/day):
  - daily() market-wide:       ~5000 pts/call (entire market for one date)
  - daily_basic(trade_date):   ~1100 pts/call (5000 stocks × 0.2)
  - income_vip per stock:      ~5 pts
  - balancesheet_vip per stock: ~5 pts

  Typical daily budget:
    bars    : 1 date/day  → ~5000 pts  (only mode that eats the budget)
    fundamental: 4-5 dates/day → ~4500-5500 pts
    financials: 500 stocks × 10 pts = 5000 pts/week (weekly scheduler)

Workflow:
  Week 1: bars backfill (1 date/day, ~20 dates/week)
  Week 2: bars backfill continue + fundamental backfill (4-5 dates/day)
  Week 3+: financials (handled by weekly scheduler, batch_size=500)
"""

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy.dialects.postgresql import insert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_a_stock")


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def parse_date(value: str) -> date:
    """Parse YYYYMMDD → date; raise for bad input."""
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except (ValueError, IndexError):
        raise argparse.ArgumentTypeError(f"Invalid date '{value}'. Use YYYYMMDD.")


def date_range(start: date, end: date) -> list[date]:
    """Yield every calendar date in [start, end] inclusive."""
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


# ---------------------------------------------------------------------------
# Bar backfill (daily OHLCV)
# ---------------------------------------------------------------------------


def backfill_bars(
    db,
    start: date,
    end: date,
    dry_run: bool = False,
    rate_limit: float = 0.5,
) -> dict:
    """Backfill etf_daily_bar using market-wide bulk endpoint.

    One API call per calendar date. Non-trading days will return empty
    and are skipped automatically.
    """
    from app.data.providers.tushare_provider import TushareProvider
    from app.models.etf import ETFDailyBar, ETFInfo

    provider = TushareProvider()

    # Pre-load known A-share stock codes
    known_codes: set[str] = set(
        row[0]
        for row in db.query(ETFInfo.code)
        .filter(ETFInfo.market == "A股", ETFInfo.instrument_type == "STOCK")
        .all()
    )
    logger.info("Known A-share stock codes: %d", len(known_codes))
    if not known_codes:
        logger.error("No A-share stocks registered. Run discovery pipeline first.")
        return {"total_dates": 0, "trading_dates": 0, "records": 0, "errors": []}

    dates = date_range(start, end)
    total_dates = len(dates)
    trading_dates = 0
    total_records = 0
    errors: list[str] = []

    for i, trade_date in enumerate(dates):
        label = f"[{i + 1}/{total_dates}] {trade_date}"
        print(f"  {label} ...", end=" ", flush=True)

        if dry_run:
            print("DRY-RUN (skipped)")
            continue

        try:
            df = provider.fetch_daily_all_market(trade_date)
        except Exception as exc:
            msg = f"API error: {exc}"
            print(f"FAILED — {msg}")
            errors.append(f"{trade_date}: {msg}")
            time.sleep(rate_limit)
            continue

        if df is None or df.empty:
            print("no data (non-trading day)")
            time.sleep(rate_limit)
            continue

        # Filter to known codes
        df = df[df["etf_code"].isin(known_codes)].copy()
        if df.empty:
            print("no data after filtering")
            time.sleep(rate_limit)
            continue

        # Build records & upsert
        records = _df_to_bar_records(df)
        if not records:
            print("no valid records")
            time.sleep(rate_limit)
            continue

        try:
            stmt = (
                insert(ETFDailyBar)
                .values(records)
                .on_conflict_do_update(
                    index_elements=["etf_code", "trade_date"],
                    set_={
                        "open": insert(ETFDailyBar).excluded.open,
                        "high": insert(ETFDailyBar).excluded.high,
                        "low": insert(ETFDailyBar).excluded.low,
                        "close": insert(ETFDailyBar).excluded.close,
                        "volume": insert(ETFDailyBar).excluded.volume,
                        "amount": insert(ETFDailyBar).excluded.amount,
                        "pre_close": insert(ETFDailyBar).excluded.pre_close,
                        "change_pct": insert(ETFDailyBar).excluded.change_pct,
                        "turnover_rate": insert(ETFDailyBar).excluded.turnover_rate,
                    },
                )
            )
            db.execute(stmt)
            db.commit()
            trading_dates += 1
            total_records += len(records)
            print(f"OK ({len(records)} stocks)")
        except Exception as exc:
            db.rollback()
            msg = f"DB error: {exc}"
            print(f"FAILED — {msg}")
            errors.append(f"{trade_date}: {msg}")

        time.sleep(rate_limit)

    return {
        "total_dates": total_dates,
        "trading_dates": trading_dates,
        "records": total_records,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Per-stock bar backfill (for deep historical ranges like 2010+)
# ---------------------------------------------------------------------------


def backfill_bars_per_stock(
    db,
    start: date,
    end: date,
    batch_size: int = 500,
    batch_offset: int = 0,
    dry_run: bool = False,
    rate_limit: float = 0.5,
) -> dict:
    """Backfill etf_daily_bar using per-stock API calls for deep history.

    Unlike ``backfill_bars`` which uses the market-wide endpoint (1 call/date,
    ~5000 pts/call — economical for recent dates), this function calls
    ``pro.daily(ts_code=xxx, start_date=..., end_date=...)`` per stock.

    **Point budget** (Tushare free tier, ~5000 pts/day):
      - Per-stock daily call: ~5 pts (returns ALL days for one stock)
      - 500 stocks × 5 pts = 2500 pts per batch
      - Full 6030 stocks = ~30,000 pts = 6 days at 1000 stocks/day

    Use this for filling 2010–2024 data where the market-wide approach
    (4250 dates × 5000 pts) would be impossibly expensive.

    Args:
        start, end: Date range for daily bars (e.g. 2010-01-01 → 2026-06-27).
        batch_size: Stocks per run (default 500, ~2500 pts).
        batch_offset: Starting offset into sorted stock list.
    """
    from app.data.providers.tushare_provider import TushareProvider
    from app.models.etf import ETFDailyBar, ETFInfo

    provider = TushareProvider()

    # Pre-load active A-share stock codes
    stocks = (
        db.query(ETFInfo)
        .filter(ETFInfo.market == "A股")
        .filter(ETFInfo.instrument_type == "STOCK")
        .filter(ETFInfo.status == "active")
        .order_by(ETFInfo.code)
        .all()
    )
    all_codes = [s.code for s in stocks]
    logger.info("Active A-share stocks: %d total", len(all_codes))
    if not all_codes:
        logger.error("No active A-share stocks registered.")
        return {"total_stocks": 0, "processed": 0, "records": 0, "errors": []}

    total_stocks = len(all_codes)
    batch = all_codes[batch_offset : batch_offset + batch_size]
    logger.info(
        "Per-stock bar backfill: batch [%d:%d] (%d stocks), %s → %s",
        batch_offset, batch_offset + len(batch), len(batch), start, end,
    )

    total_records = 0
    processed = 0
    errors: list[str] = []

    for i, code in enumerate(batch):
        label = f"[{batch_offset + i + 1}/{total_stocks}] {code}"
        print(f"  {label} ...", end=" ", flush=True)

        if dry_run:
            print("DRY-RUN")
            continue

        try:
            df = provider.fetch_daily_bars(
                codes=[code], start_date=start, end_date=end,
            )
        except Exception as exc:
            msg = f"API error: {exc}"
            print(f"FAILED — {msg}")
            errors.append(f"{code}: {msg}")
            db.rollback()
            time.sleep(rate_limit)
            continue

        if df is None or df.empty:
            print("no data")
            time.sleep(rate_limit)
            continue

        records = _df_to_bar_records(df)
        if not records:
            print("no valid records")
            time.sleep(rate_limit)
            continue

        try:
            stmt = (
                insert(ETFDailyBar)
                .values(records)
                .on_conflict_do_update(
                    index_elements=["etf_code", "trade_date"],
                    set_={
                        "open": insert(ETFDailyBar).excluded.open,
                        "high": insert(ETFDailyBar).excluded.high,
                        "low": insert(ETFDailyBar).excluded.low,
                        "close": insert(ETFDailyBar).excluded.close,
                        "volume": insert(ETFDailyBar).excluded.volume,
                        "amount": insert(ETFDailyBar).excluded.amount,
                        "pre_close": insert(ETFDailyBar).excluded.pre_close,
                        "change_pct": insert(ETFDailyBar).excluded.change_pct,
                        "turnover_rate": insert(ETFDailyBar).excluded.turnover_rate,
                    },
                )
            )
            db.execute(stmt)
            db.commit()
            processed += 1
            total_records += len(records)
            print(f"OK ({len(records)} days)")
        except Exception as exc:
            db.rollback()
            msg = f"DB error: {exc}"
            print(f"FAILED — {msg}")
            errors.append(f"{code}: {msg}")

        time.sleep(rate_limit)

    return {
        "total_stocks": total_stocks,
        "processed": processed,
        "records": total_records,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Fundamental backfill (PE/PB/market cap via daily_basic)
# ---------------------------------------------------------------------------


def backfill_fundamental(
    db,
    start: date,
    end: date,
    dry_run: bool = False,
    rate_limit: float = 0.5,
) -> dict:
    """Backfill stock_fundamental using daily_basic market-wide endpoint.

    One API call per calendar date. Returns PE, PB, market cap, turnover,
    share counts for all A-share stocks on that date.
    """
    from app.data.providers.tushare_provider import TushareProvider
    from app.models.etf import ETFInfo, StockFundamental

    provider = TushareProvider()

    known_codes: set[str] = set(
        row[0]
        for row in db.query(ETFInfo.code)
        .filter(ETFInfo.market == "A股", ETFInfo.instrument_type == "STOCK")
        .all()
    )
    logger.info("Known A-share stock codes: %d", len(known_codes))

    dates = date_range(start, end)
    total_dates = len(dates)
    trading_dates = 0
    total_records = 0
    errors: list[str] = []

    field_map: list[tuple[str, str]] = [
        ("etf_code", "stock_code"),
        ("trade_date", "trade_date"),
        ("pe_ttm", "pe_ttm"),
        ("pb", "pb"),
        ("total_mv", "total_mv"),
        ("circ_mv", "circ_mv"),
        ("turnover_rate_f", "turnover_rate_f"),
        ("volume_ratio", "volume_ratio"),
        ("total_share", "total_share"),
        ("float_share", "float_share"),
        ("free_share", "free_share"),
    ]

    for i, trade_date in enumerate(dates):
        label = f"[{i + 1}/{total_dates}] {trade_date}"
        print(f"  {label} ...", end=" ", flush=True)

        if dry_run:
            print("DRY-RUN (skipped)")
            continue

        try:
            df = provider.fetch_daily_basic(trade_date=trade_date)
        except Exception as exc:
            msg = f"API error: {exc}"
            print(f"FAILED — {msg}")
            errors.append(f"{trade_date}: {msg}")
            time.sleep(rate_limit)
            continue

        if df is None or df.empty:
            print("no data (non-trading day)")
            time.sleep(rate_limit)
            continue

        # Filter to known codes
        df = df[df["etf_code"].isin(known_codes)].copy()
        if df.empty:
            print("no data after filtering")
            time.sleep(rate_limit)
            continue

        records = []
        for _, row in df.iterrows():
            record = {}
            for src_col, dst_col in field_map:
                val = row.get(src_col)
                if val is None or pd.isna(val):
                    record[dst_col] = None
                else:
                    record[dst_col] = val
            if record.get("stock_code") and record.get("trade_date"):
                records.append(record)

        if not records:
            print("no valid records")
            time.sleep(rate_limit)
            continue

        try:
            stmt = (
                insert(StockFundamental)
                .values(records)
                .on_conflict_do_update(
                    index_elements=["stock_code", "trade_date"],
                    set_={
                        "pe_ttm": insert(StockFundamental).excluded.pe_ttm,
                        "pb": insert(StockFundamental).excluded.pb,
                        "total_mv": insert(StockFundamental).excluded.total_mv,
                        "circ_mv": insert(StockFundamental).excluded.circ_mv,
                        "turnover_rate_f": insert(StockFundamental).excluded.turnover_rate_f,
                        "volume_ratio": insert(StockFundamental).excluded.volume_ratio,
                        "total_share": insert(StockFundamental).excluded.total_share,
                        "float_share": insert(StockFundamental).excluded.float_share,
                        "free_share": insert(StockFundamental).excluded.free_share,
                    },
                )
            )
            db.execute(stmt)
            db.commit()
            trading_dates += 1
            total_records += len(records)
            print(f"OK ({len(records)} stocks)")
        except Exception as exc:
            db.rollback()
            msg = f"DB error: {exc}"
            print(f"FAILED — {msg}")
            errors.append(f"{trade_date}: {msg}")

        time.sleep(rate_limit)

    return {
        "total_dates": total_dates,
        "trading_dates": trading_dates,
        "records": total_records,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Financials backfill (income + balance sheet, per-stock)
# ---------------------------------------------------------------------------


def backfill_financials(
    db,
    batch_size: int = 500,
    batch_offset: int = 0,
    dry_run: bool = False,
    rate_limit: float = 0.5,
    start_date: date | None = None,
) -> dict:
    """Backfill stock_income + stock_balance_sheet using per-stock API calls.

    Each stock requires 2 API calls (income_vip + balancesheet_vip).
    At ~5000 points/day and ~10 pts/stock, budget allows ~500 stocks/day.

    Args:
        batch_size: Number of stocks to process in this run.
        batch_offset: Starting offset into the sorted stock list (0-based).
        start_date: If set, fetch from this date (e.g. 2010-01-01) instead of
                    the latest 4 reports. Useful for historical backfill.
    """
    from app.data.providers.tushare_provider import TushareProvider
    from app.models.etf import ETFInfo, StockBalanceSheet, StockIncome

    provider = TushareProvider()

    stocks = (
        db.query(ETFInfo)
        .filter(ETFInfo.market == "A股")
        .filter(ETFInfo.instrument_type == "STOCK")
        .filter(ETFInfo.status == "active")
        .order_by(ETFInfo.code)
        .all()
    )

    total_stocks = len(stocks)
    batch = stocks[batch_offset : batch_offset + batch_size]
    codes = [s.code for s in batch]

    logger.info(
        "Financials backfill: %d total, batch [%d:%d] (%d stocks)",
        total_stocks, batch_offset, batch_offset + len(batch), len(codes),
    )

    income_records = 0
    bs_records = 0
    income_errors = 0
    bs_errors = 0

    income_field_map: list[tuple[str, str]] = [
        ("etf_code", "stock_code"),
        ("end_date", "end_date"),
        ("report_type", "report_type"),
        ("ann_date", "ann_date"),
        ("total_revenue", "total_revenue"),
        ("revenue_yoy", "revenue_yoy"),
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

    bs_field_map: list[tuple[str, str]] = [
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

    for i, code in enumerate(codes):
        label = f"  [{i + 1}/{len(codes)}] {code}"
        print(f"  {label} ...", end=" ", flush=True)

        if dry_run:
            print("DRY-RUN")
            continue

        # ── Income Statement ──
        inc_added = 0
        try:
            df_income = provider.fetch_income_vip(
                code, start_date=start_date, limit=200 if start_date else 4,
            )
            if df_income is not None and not df_income.empty:
                # Build records, dedup by (stock_code, end_date, report_type)
                inc_records = []
                seen = set()
                for _, row in df_income.iterrows():
                    key = (row.get("etf_code"), row.get("end_date"), row.get("report_type"))
                    if key in seen:
                        continue
                    seen.add(key)
                    record = {}
                    for src_col, dst_col in income_field_map:
                        val = row.get(src_col)
                        if val is not None and not (isinstance(val, float) and pd.isna(val)):
                            record[dst_col] = val
                        else:
                            record[dst_col] = None  # required for excluded.<col> resolution
                    if record.get("stock_code") and record.get("end_date"):
                        inc_records.append(record)

                if inc_records:
                    if not dry_run:
                        stmt = (
                            insert(StockIncome)
                            .values(inc_records)
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
                        db.execute(stmt)
                        db.commit()
                    inc_added = len(inc_records)
                    income_records += inc_added

        except Exception as exc:
            income_errors += 1
            db.rollback()
            logger.warning("income_vip(%s) failed: %s", code, exc)

        time.sleep(rate_limit)

        # ── Balance Sheet ──
        bs_added = 0
        try:
            df_bs = provider.fetch_balancesheet_vip(
                code, start_date=start_date, limit=200 if start_date else 4,
            )
            if df_bs is not None and not df_bs.empty:
                bs_recs = []
                seen = set()
                for _, row in df_bs.iterrows():
                    key = (row.get("etf_code"), row.get("end_date"), row.get("report_type"))
                    if key in seen:
                        continue
                    seen.add(key)
                    record = {}
                    for src_col, dst_col in bs_field_map:
                        val = row.get(src_col)
                        if val is not None and not (isinstance(val, float) and pd.isna(val)):
                            record[dst_col] = val
                        else:
                            record[dst_col] = None  # required for excluded.<col> resolution
                    if record.get("stock_code") and record.get("end_date"):
                        bs_recs.append(record)

                if bs_recs:
                    if not dry_run:
                        stmt = (
                            insert(StockBalanceSheet)
                            .values(bs_recs)
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
                        db.execute(stmt)
                        db.commit()
                    bs_added = len(bs_recs)
                    bs_records += bs_added

        except Exception as exc:
            bs_errors += 1
            db.rollback()
            logger.warning("balancesheet_vip(%s) failed: %s", code, exc)

        time.sleep(rate_limit)

        if inc_added or bs_added:
            print(f"OK (income={inc_added}, bs={bs_added})")
        else:
            print("no data")

    return {
        "stocks_processed": len(codes),
        "income_records": income_records,
        "bs_records": bs_records,
        "income_errors": income_errors,
        "bs_errors": bs_errors,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_BAR_FIELDS = [
    "etf_code", "trade_date", "open", "high", "low", "close",
    "volume", "amount", "pre_close", "change_pct", "turnover_rate",
]


def _df_to_bar_records(df: pd.DataFrame) -> list[dict]:
    """Convert a standardized daily bars DataFrame to upsert-ready records.

    All fields are always included (None where missing) so that the
    ON CONFLICT … SET excluded.<col> references always resolve.

    ``change_pct`` is capped to the ``DECIMAL(8, 4)`` range so that extreme
    outliers (e.g. BJ stocks jumping from 0.01 to 20.05) do not trigger a
    numeric overflow on INSERT.
    """
    # DECIMAL(8, 4) supports values in [-9999.9999, 9999.9999]
    _MAX_CHANGE_PCT = 9999.9999
    _MIN_CHANGE_PCT = -9999.9999

    records = []
    for _, row in df.iterrows():
        record = {f: row.get(f) for f in _BAR_FIELDS}

        cp = record.get("change_pct")
        if cp is not None and not (isinstance(cp, float) and pd.isna(cp)):
            try:
                cp = float(cp)
                if cp > _MAX_CHANGE_PCT:
                    cp = _MAX_CHANGE_PCT
                elif cp < _MIN_CHANGE_PCT:
                    cp = _MIN_CHANGE_PCT
                record["change_pct"] = cp
            except (ValueError, TypeError):
                record["change_pct"] = None
        else:
            record["change_pct"] = None

        records.append(record)
    return records


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Backfill A-share individual stock historical data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --mode bars --start 20260102 --end 20260131
  %(prog)s --mode fundamental --start 20260301 --end 20260331
  %(prog)s --mode financials --batch-size 500 --batch-offset 0
  %(prog)s --mode all --start 20260601 --end 20260628
  %(prog)s --mode bars --start 20260101 --end 20260630 --dry-run
        """,
    )
    parser.add_argument(
        "--mode", choices=["bars", "bars-stock", "fundamental", "financials", "all"],
        default="all",
        help="Data type to backfill (default: all = bars + fundamental). "
             "bars-stock uses per-stock API for deep history.",
    )
    parser.add_argument(
        "--start", type=parse_date, default=None,
        help="Start date YYYYMMDD (required for bars/bars-stock/fundamental/all)",
    )
    parser.add_argument(
        "--end", type=parse_date, default=None,
        help="End date YYYYMMDD (required for bars/bars-stock/fundamental/all)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=500,
        help="Stocks per run for financials/bars-stock (default: 500)",
    )
    parser.add_argument(
        "--batch-offset", type=int, default=0,
        help="Starting offset for financials/bars-stock (default: 0)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Scan dates without writing to database",
    )
    parser.add_argument(
        "--rate-limit", type=float, default=0.5,
        help="Seconds between API calls (default: 0.5)",
    )
    args = parser.parse_args()

    # Validate args
    if args.mode in ("bars", "bars-stock", "fundamental", "all"):
        if args.start is None or args.end is None:
            parser.error(f"--start and --end are required for --mode {args.mode}")
        if args.start > args.end:
            parser.error(f"--start ({args.start}) must be <= --end ({args.end})")

    # ── Run ──────────────────────────────────────────────────────
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        start_time = time.monotonic()

        if args.mode == "bars":
            print("=" * 60)
            print(f"Backfill: DAILY BARS  |  {args.start} → {args.end}")
            if args.dry_run:
                print("DRY RUN — no writes")
            print("=" * 60)
            result = backfill_bars(
                db, args.start, args.end,
                dry_run=args.dry_run, rate_limit=args.rate_limit,
            )
            _print_summary("Daily Bars", result)

        elif args.mode == "bars-stock":
            print("=" * 60)
            print(
                f"Backfill: DAILY BARS (per-stock)  |  {args.start} → {args.end}  |  "
                f"batch={args.batch_size}, offset={args.batch_offset}"
            )
            if args.dry_run:
                print("DRY RUN — no writes")
            print("=" * 60)
            result = backfill_bars_per_stock(
                db,
                start=args.start,
                end=args.end,
                batch_size=args.batch_size,
                batch_offset=args.batch_offset,
                dry_run=args.dry_run,
                rate_limit=args.rate_limit,
            )
            _print_bars_stock_summary(result)

        elif args.mode == "fundamental":
            print("=" * 60)
            print(f"Backfill: FUNDAMENTALS  |  {args.start} → {args.end}")
            if args.dry_run:
                print("DRY RUN — no writes")
            print("=" * 60)
            result = backfill_fundamental(
                db, args.start, args.end,
                dry_run=args.dry_run, rate_limit=args.rate_limit,
            )
            _print_summary("Fundamentals", result)

        elif args.mode == "financials":
            print("=" * 60)
            print(
                f"Backfill: FINANCIALS  |  batch={args.batch_size}, "
                f"offset={args.batch_offset}"
            )
            if args.dry_run:
                print("DRY RUN — no writes")
            print("=" * 60)
            result = backfill_financials(
                db,
                batch_size=args.batch_size,
                batch_offset=args.batch_offset,
                dry_run=args.dry_run,
                rate_limit=args.rate_limit,
                start_date=args.start,
            )
            _print_financials_summary(result)

        elif args.mode == "all":
            print("=" * 60)
            print(f"Backfill: ALL (bars + fundamental)  |  {args.start} → {args.end}")
            if args.dry_run:
                print("DRY RUN — no writes")
            print("=" * 60)

            # Bars first
            print("\n── Step 1/2: Daily Bars ──")
            bar_result = backfill_bars(
                db, args.start, args.end,
                dry_run=args.dry_run, rate_limit=args.rate_limit,
            )
            _print_summary("Daily Bars", bar_result)

            # Fundamentals second
            print("\n── Step 2/2: Fundamentals ──")
            fund_result = backfill_fundamental(
                db, args.start, args.end,
                dry_run=args.dry_run, rate_limit=args.rate_limit,
            )
            _print_summary("Fundamentals", fund_result)

        elapsed = time.monotonic() - start_time
        print(f"\nTotal elapsed: {elapsed:.0f}s")

    finally:
        db.close()


def _print_summary(label: str, result: dict):
    print()
    print(f"── {label} Summary ──")
    print(f"  Dates scanned:    {result['total_dates']}")
    print(f"  Trading dates:    {result['trading_dates']}")
    print(f"  Records upserted: {result['records']:,}")
    if result.get("errors"):
        print(f"  Errors:           {len(result['errors'])}")
        for err in result["errors"][:5]:
            print(f"    - {err}")
        if len(result["errors"]) > 5:
            print(f"    ... and {len(result['errors']) - 5} more")


def _print_financials_summary(result: dict):
    print()
    print("── Financials Summary ──")
    print(f"  Stocks processed: {result['stocks_processed']}")
    print(f"  Income records:   {result['income_records']}")
    print(f"  Balance records:  {result['bs_records']}")
    print(f"  Income errors:    {result['income_errors']}")
    print(f"  BS errors:        {result['bs_errors']}")


def _print_bars_stock_summary(result: dict):
    print()
    print("── Per-Stock Daily Bars Summary ──")
    print(f"  Total stocks:     {result['total_stocks']}")
    print(f"  Processed:        {result['processed']}")
    print(f"  Records upserted: {result['records']:,}")
    if result.get("errors"):
        print(f"  Errors:           {len(result['errors'])}")
        for err in result["errors"][:5]:
            print(f"    - {err}")
        if len(result["errors"]) > 5:
            print(f"    ... and {len(result['errors']) - 5} more")


if __name__ == "__main__":
    main()
