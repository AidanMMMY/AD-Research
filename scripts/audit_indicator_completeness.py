#!/usr/bin/env python3
"""A 股 ETF 指标完整性审计脚本。

校验指定交易日（或 A 股最新交易日）的 `etf_indicator` 对 `instrument_daily_bar`
中 A 股 ETF 的覆盖情况，用于 CI/健康检查/日常巡检。

环境变量:
    DATABASE_URL: PostgreSQL 连接字符串，例如
                  postgresql://user:pass@localhost:5432/ad_research

用法:
    python scripts/audit_indicator_completeness.py
    python scripts/audit_indicator_completeness.py --date 2026-07-17

退出码:
    0  OK       覆盖率 >= 95%
    1  WARN     90% <= 覆盖率 < 95%
    1  CRITICAL 覆盖率 < 90%
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


# 阈值与状态映射
THRESHOLD_WARN = 0.95
THRESHOLD_CRITICAL = 0.90


def get_latest_a_share_trading_date(engine: Engine) -> date:
    """返回 A 股（market='A股'）在日线表中最新交易日。"""
    sql = text(
        """
        SELECT MAX(b.trade_date) AS latest_date
        FROM instrument_daily_bar b
        JOIN etf_info i ON i.code = b.etf_code
        WHERE i.market = 'A股'
        """
    )
    with engine.connect() as conn:
        row = conn.execute(sql).fetchone()
    latest = row[0] if row else None
    if latest is None:
        raise RuntimeError("未找到 A 股日线数据，无法确定最新交易日")
    return latest


def audit(engine: Engine, target_date: date) -> dict:
    """执行审计查询并返回结构化结果。"""
    # 1) 当日 A 股日线总条数
    total_sql = text(
        """
        SELECT COUNT(*)
        FROM instrument_daily_bar b
        JOIN etf_info i ON i.code = b.etf_code
        WHERE i.market = 'A股' AND b.trade_date = :trade_date
        """
    )

    # 2) 当日已有指标条数（仅统计 A 股代码）
    covered_sql = text(
        """
        SELECT COUNT(*)
        FROM etf_indicator ind
        JOIN etf_info i ON i.code = ind.etf_code
        WHERE i.market = 'A股' AND ind.trade_date = :trade_date
        """
    )

    # 3) 按前缀统计覆盖率
    prefix_sql = text(
        """
        SELECT
            LEFT(b.etf_code, 1) AS prefix,
            COUNT(DISTINCT b.etf_code) AS total_codes,
            COUNT(DISTINCT ind.etf_code) AS covered_codes
        FROM instrument_daily_bar b
        JOIN etf_info i ON i.code = b.etf_code
        LEFT JOIN etf_indicator ind
            ON ind.etf_code = b.etf_code
            AND ind.trade_date = b.trade_date
        WHERE i.market = 'A股' AND b.trade_date = :trade_date
        GROUP BY LEFT(b.etf_code, 1)
        ORDER BY prefix
        """
    )

    # 4) 缺失代码列表（前 50）
    missing_sql = text(
        """
        SELECT DISTINCT b.etf_code
        FROM instrument_daily_bar b
        JOIN etf_info i ON i.code = b.etf_code
        LEFT JOIN etf_indicator ind
            ON ind.etf_code = b.etf_code
            AND ind.trade_date = b.trade_date
        WHERE i.market = 'A股'
          AND b.trade_date = :trade_date
          AND ind.etf_code IS NULL
        ORDER BY b.etf_code
        LIMIT 50
        """
    )

    with engine.connect() as conn:
        total = conn.execute(total_sql, {"trade_date": target_date}).scalar() or 0
        covered = conn.execute(covered_sql, {"trade_date": target_date}).scalar() or 0
        prefix_rows = conn.execute(prefix_sql, {"trade_date": target_date}).fetchall()
        missing_rows = conn.execute(missing_sql, {"trade_date": target_date}).fetchall()

    coverage = covered / total if total else 0.0

    if coverage >= THRESHOLD_WARN:
        status = "OK"
    elif coverage >= THRESHOLD_CRITICAL:
        status = "WARN"
    else:
        status = "CRITICAL"

    return {
        "trade_date": target_date,
        "total": total,
        "covered": covered,
        "missing": total - covered,
        "coverage": coverage,
        "status": status,
        "prefixes": [
            {
                "prefix": row[0],
                "total": row[1],
                "covered": row[2],
                "missing": row[1] - row[2],
                "coverage": (row[2] / row[1]) if row[1] else 0.0,
            }
            for row in prefix_rows
        ],
        "missing_codes": [row[0] for row in missing_rows],
    }


def print_report(result: dict) -> None:
    """打印审计结果。"""
    sep = "=" * 60
    print(sep)
    print(f"A 股 ETF 指标完整性审计 | 交易日: {result['trade_date']}")
    print(sep)
    print(f"整体状态: {result['status']}")
    print(f"日线总条数: {result['total']:,}")
    print(f"指标覆盖条数: {result['covered']:,}")
    print(f"缺失条数: {result['missing']:,}")
    print(f"总覆盖率: {result['coverage']:.2%}")
    print("-" * 60)
    print("按前缀覆盖率:")
    print(f"  {'前缀':<6} {'日线':>8} {'指标':>8} {'缺失':>8} {'覆盖率':>8}")
    for p in result["prefixes"]:
        print(
            f"  {p['prefix']:<6} {p['total']:>8,} {p['covered']:>8,} "
            f"{p['missing']:>8,} {p['coverage']:>7.2%}"
        )
    print("-" * 60)
    print(f"缺失 etf_code 列表（前 {len(result['missing_codes'])} 个）:")
    for code in result["missing_codes"]:
        print(f"  - {code}")
    if not result["missing_codes"]:
        print("  (无)")
    print(sep)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="审计 A 股 ETF 指标（etf_indicator）对日线（instrument_daily_bar）的覆盖情况。"
    )
    parser.add_argument(
        "--date",
        type=str,
        metavar="YYYY-MM-DD",
        help="指定审计日期；默认取 A 股最新交易日",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("错误: 请设置 DATABASE_URL 环境变量", file=sys.stderr)
        return 1

    engine = create_engine(database_url, future=True)

    if args.date:
        try:
            target_date = date.fromisoformat(args.date)
        except ValueError:
            print(f"错误: --date 格式应为 YYYY-MM-DD，收到: {args.date}", file=sys.stderr)
            return 1
    else:
        target_date = get_latest_a_share_trading_date(engine)

    result = audit(engine, target_date)
    print_report(result)

    # OK 返回 0；WARN/CRITICAL 返回 1，便于 CI 触发告警
    return 0 if result["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
