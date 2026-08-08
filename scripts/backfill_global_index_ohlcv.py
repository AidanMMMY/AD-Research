#!/usr/bin/env python3
"""回填全球速览指数 OHLCV 全历史（global_index_daily_bar）.

详情页上线前的一次性脚本：

* yfinance 路径 — 遍历 GLOBAL_INDEX + FOREX + COMMODITY 三个
  registry（RATES 留给 FRED 折线），用 ``--period``（默认 10y）
  拉全历史日线。
* akshare 路径 — 遍历 A_SHARE_INDEX_REGISTRY，
  ``lookback_days=None`` 拉全历史。

用法::

    python scripts/backfill_global_index_ohlcv.py --dry-run
    python scripts/backfill_global_index_ohlcv.py --source yfinance --period 10y
    python scripts/backfill_global_index_ohlcv.py --codes global_sp500,global_shcomp

``--dry-run`` 只打印每 code 的行数，不写库。
"""

import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--period",
        default="10y",
        help="yfinance history period 参数（默认 10y，拉全历史）",
    )
    parser.add_argument(
        "--codes",
        default=None,
        help="逗号分隔的内部 code 过滤子集（如 global_sp500,global_shcomp）",
    )
    parser.add_argument(
        "--source",
        choices=["yfinance", "akshare", "all"],
        default="all",
        help="回填哪个来源（默认 all）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印每 code 行数，不入库",
    )
    args = parser.parse_args()

    codes = [c.strip() for c in args.codes.split(",")] if args.codes else None

    # 注意：app.db 模块不存在，SessionLocal 从这里拿（项目已知坑）
    from app.services.macro.global_index_bar_service import GlobalIndexBarService
    from app.services.macro.global_indices_fetcher import (
        A_SHARE_INDEX_REGISTRY,
        fetch_a_share_ohlcv,
    )
    from app.tasks.cninfo import SessionLocal

    all_bars: list[dict] = []

    if args.source in ("yfinance", "all"):
        from app.data.providers.yfinance_indices_provider import (
            fetch_yfinance_ohlcv_bars,
        )

        print(f"=== yfinance OHLCV 回填 (period={args.period}) ===")
        yf_bars = fetch_yfinance_ohlcv_bars(period=args.period, codes=codes)
        all_bars.extend(yf_bars)
        print(f"yfinance 共抓取 {len(yf_bars)} 行")

    if args.source in ("akshare", "all"):
        print("=== akshare A股指数 OHLCV 回填 (全历史) ===")
        ak_bars = fetch_a_share_ohlcv(lookback_days=None)
        if codes:
            code_set = set(codes)
            ak_bars = [b for b in ak_bars if b["code"] in code_set]
        all_bars.extend(ak_bars)
        print(f"akshare 共抓取 {len(ak_bars)} 行")

    # 每 code 行数汇总
    counts = Counter(b["code"] for b in all_bars)
    known_codes = {e["code"] for e in A_SHARE_INDEX_REGISTRY}
    for code in sorted(counts):
        print(f"  {code:20s} {counts[code]:6d} 行")
    missing = (set(codes) - set(counts)) if codes else set()
    if missing:
        print(f"  [warn] 以下 code 无数据: {sorted(missing)}")
    if codes:
        unknown = set(codes) - known_codes
        if unknown:
            print(f"  [info] 非 A股 registry 的 code（yfinance 路径处理）: {sorted(unknown)}")

    if args.dry_run:
        print("=== dry-run，未写库 ===")
        return

    db = SessionLocal()
    try:
        service = GlobalIndexBarService(db)
        written = service.upsert_bars(all_bars)
        print(f"=== 已 upsert {written} 行到 global_index_daily_bar ===")
    finally:
        db.close()


if __name__ == "__main__":
    main()
