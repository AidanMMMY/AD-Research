#!/usr/bin/env python3
"""把 A 股 (ETF + STOCK) 的 instrument_daily_bar.adj_factor 统一填为 1.0。

背景
----
A 股 ETF/个股在本平台「不做复权」（T+1 结算 + 无杠杆场景），所以所有 A 股
标的的 ``adj_factor`` 应当恒等于 1.0。当前数据库里部分行该字段为 NULL，
这会让下游指标计算 / 报告展示出现除零或归一化错误。

与 ``app/scripts/backfill_a_share_adj_factor.py`` 的区别
------------------------------------------------------
- ``app/scripts/...`` 是生产流水线：从 Tushare 取真实复权因子写入数据库。
- 本脚本（``scripts/...``）是临时数据修复：直接批量更新为 1.0，**不调任何
  外部 API**，仅在当前复权策略下使用。

用法
----
    # 1) 默认 dry-run，只打印待修改行数与样本
    python scripts/backfill_a_share_adj_factor.py

    # 2) 显式 dry-run（和默认一致）
    python scripts/backfill_a_share_adj_factor.py --dry-run

    # 3) 真正写入（必须显式 --commit）
    python scripts/backfill_a_share_adj_factor.py --commit
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.core.database import SessionLocal


# 目标过滤：A股 + ETF 或 STOCK
_TARGET_FILTER = """
    e.market = 'A股'
    AND e.instrument_type IN ('ETF', 'STOCK')
    AND e.status = 'active'
"""

# 只更新 NULL / 0 的行，避免误改已经合法的 1.0 / 其它值
_UPDATE_WHERE = """
    (b.adj_factor IS NULL OR b.adj_factor = 0)
"""


def _count_rows_needing_fix(db) -> dict:
    """统计需要修复的行数 + 一些样本。"""
    sql = text(
        f"""
        SELECT
            COUNT(*) AS need_fix,
            COUNT(*) FILTER (WHERE b.adj_factor IS NULL) AS null_count,
            COUNT(*) FILTER (WHERE b.adj_factor = 0)     AS zero_count,
            COUNT(DISTINCT b.etf_code)                   AS instrument_count,
            MIN(b.trade_date)                            AS min_date,
            MAX(b.trade_date)                            AS max_date
        FROM instrument_daily_bar b
        JOIN etf_info e ON e.code = b.etf_code
        WHERE {_TARGET_FILTER}
          AND {_UPDATE_WHERE}
        """
    )
    return dict(db.execute(sql).mappings().first() or {})


def _sample_rows(db, limit: int = 5) -> list[dict]:
    sql = text(
        f"""
        SELECT b.etf_code, e.name, e.instrument_type,
               b.trade_date, b.adj_factor
        FROM instrument_daily_bar b
        JOIN etf_info e ON e.code = b.etf_code
        WHERE {_TARGET_FILTER}
          AND {_UPDATE_WHERE}
        ORDER BY b.etf_code, b.trade_date
        LIMIT :limit
        """
    )
    rows = db.execute(sql, {"limit": limit}).mappings().all()
    return [dict(r) for r in rows]


def _do_update(db) -> int:
    """真正执行 UPDATE，返回受影响行数。"""
    sql = text(
        f"""
        UPDATE instrument_daily_bar AS b
        SET adj_factor = 1.0
        FROM etf_info e
        WHERE e.code = b.etf_code
          AND {_TARGET_FILTER}
          AND {_UPDATE_WHERE}
        """
    )
    result = db.execute(sql)
    db.commit()
    return result.rowcount or 0


def main():
    parser = argparse.ArgumentParser(
        description="把 A 股 ETF/STOCK 的 adj_factor 统一填为 1.0"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="只打印，不写入（默认）",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        default=False,
        help="真正写入数据库（必须显式指定）",
    )
    args = parser.parse_args()

    # --commit 隐含关闭 dry-run
    do_write = args.commit
    is_dry = not do_write

    db = SessionLocal()
    try:
        print("=" * 70)
        print("Backfill A-share adj_factor -> 1.0")
        print(f"  mode        : {'DRY-RUN' if is_dry else 'COMMIT'}")
        print(f"  target      : market='A股' AND instrument_type IN ('ETF','STOCK')")
        print(f"  fix criteria: adj_factor IS NULL OR adj_factor = 0")
        print("=" * 70)

        stats = _count_rows_needing_fix(db)
        need_fix = stats.get("need_fix", 0) or 0
        print("\n[统计] 需要修复的行:")
        print(f"  待修复行数        : {need_fix:,}")
        print(f"  其中 NULL         : {stats.get('null_count', 0):,}")
        print(f"  其中 =0           : {stats.get('zero_count', 0):,}")
        print(f"  涉及标的数        : {stats.get('instrument_count', 0):,}")
        print(f"  涉及交易日范围    : {stats.get('min_date')} ~ {stats.get('max_date')}")

        if need_fix == 0:
            print("\n[OK] 没有需要修复的行，退出。")
            return 0

        print("\n[样本] 前 5 行示例:")
        for r in _sample_rows(db, limit=5):
            print(
                f"  {r['etf_code']:<14} {r['name'][:20]:<20} "
                f"{r['instrument_type']:<6} {r['trade_date']} adj={r['adj_factor']}"
            )

        if is_dry:
            print("\n[DRY-RUN] 未写入。要真正写入，请加 --commit。")
            print(
                "  示例: python scripts/backfill_a_share_adj_factor.py --commit"
            )
            return 0

        print("\n[COMMIT] 开始 UPDATE...")
        updated = _do_update(db)
        print(f"[OK] 已写入 {updated:,} 行。")

        # 写后再统计一遍，确认没遗漏
        after = _count_rows_needing_fix(db)
        remaining = after.get("need_fix", 0) or 0
        print(f"[验证] 剩余待修复行: {remaining:,}")
        if remaining:
            print("  WARN: 还有遗留行，请人工检查。")
            return 1
        return 0

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())