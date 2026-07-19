#!/usr/bin/env python3
"""回补 ``market_fund_flow`` 表。

用法
----
    # 默认回补最近 30 个交易日（dry-run）
    python scripts/backfill_market_fund_flow.py

    # 指定日期范围
    python scripts/backfill_market_fund_flow.py --start-date 2026-06-01 --end-date 2026-07-18

    # 真正写入（去掉 --dry-run）
    python scripts/backfill_market_fund_flow.py --start-date 2026-06-01 --end-date 2026-07-18

    # 仅预览
    python scripts/backfill_market_fund_flow.py --start-date 2026-06-01 --end-date 2026-07-18 --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.data.pipelines.market_fund_flow import MarketFundFlowPipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill market_fund_flow from akshare"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="起始日期 (YYYY-MM-DD); 默认 30 个交易日前的今天",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="结束日期 (YYYY-MM-DD); 默认今天",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅统计待写入行数，不提交事务",
    )
    args = parser.parse_args()

    end = date.fromisoformat(args.end_date) if args.end_date else date.today()
    start = (
        date.fromisoformat(args.start_date)
        if args.start_date
        else end - timedelta(days=30)
    )
    if start > end:
        start, end = end, start

    db = SessionLocal()
    try:
        pipeline = MarketFundFlowPipeline(
            db,
            target_date=end,
            lookback_days=(end - start).days,
            dry_run=args.dry_run,
        )
        result = pipeline.run_with_retry(max_attempts=2)
        print(
            f"Backfill market_fund_flow ({start} ~ {end}, dry_run={args.dry_run}): "
            f"success={result.success}, records={result.records}, "
            f"warnings={result.warnings}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
