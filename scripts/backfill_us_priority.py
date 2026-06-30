#!/usr/bin/env python3
"""生成美股「优先级回填清单」（CSV），不实际触发数据回填。

背景
----
当前 US 标的 569 只中只有约 41% 有日线数据。现有 ``app/data/pipelines/
us_backfill.py`` 是「按 code 字典序 + Redis 偏移」轮询的：一旦某只标的有
任何一天的数据，它就和完全没数据的标的混在一起轮换——优先级缺失。

本脚本**不**触发回填，只产出按梯队排序的清单（CSV），便于：
- 业务方挑选优先需要数据的标的；
- 给 ETL 团队作为「下一批 batch」的参考；
- 不直接修改 ``us_backfill.py`` 的轮询逻辑（那会牵动生产调度）。

梯队定义
--------
Tier 1: S&P 500 成分股。识别方法：
        ``etf_info.instrument_type = 'STOCK' AND etf_info.market = 'US'``
        （由 ``app/data/pipelines/us_stock_discovery.py`` 从 FMP S&P 500 列表写入）
Tier 2: QQQ 重仓 ETF（硬编码 top 30 名单；QQQ 持仓变化不频繁，季度复审即可）
Tier 3: 道琼斯 30 指数 ETF（DIA / DOG 等跟踪 ETF，30 只成分股硬编码）
Tier 4: 美股大盘 ETF（underlying_index LIKE '%S&P%' / 'Dow%' / 'Nasdaq%'）
Tier 5: 其他 active ETF
Tier 6: 其他 active STOCK（不在 S&P 500 列表里的美股个股 — 当前应为空）

用法
----
    # 默认：dry-run 模式，按优先级打印前 100，并写 CSV 到 reports/
    python scripts/backfill_us_priority.py

    # 只打印 Tier 1（S&P 500）
    python scripts/backfill_us_priority.py --tier 1

    # 限制输出条数
    python scripts/backfill_us_priority.py --limit 50

    # 指定输出 CSV 路径
    python scripts/backfill_us_priority.py --csv reports/my_priority.csv

注意：本脚本**只读** etf_info / instrument_daily_bar，**不写**任何数据。
"""

import argparse
import csv
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, text

from app.core.database import SessionLocal
from app.models.etf import ETFInfo, InstrumentDailyBar


# Tier 2: QQQ 重仓 ETF (粗略 Top 30 — 季度复审)
# 数据来源：公开的 Invesco QQQ Holdings 季度披露（截至 2025-2026）
QQQ_TOP_HOLDINGS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "TSLA",
    "AVGO", "COST", "NFLX", "AMD", "PEP", "CSCO", "TMUS", "INTC",
    "QCOM", "INTU", "TXN", "AMGN", "ISRG", "HON", "BKNG", "SBUX",
    "GILD", "ADP", "VRTX", "REGN", "MDLZ", "PANW",
]

# Tier 3: 道琼斯 30 指数成分股（截至 2025-2026，季度复审）
DOW30_CONSTITUENTS = [
    "AAPL", "AMGN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX",
    "DIS", "DOW", "GS", "HD", "HON", "IBM", "INTC", "JNJ",
    "JPM", "KO", "MCD", "MMM", "MRK", "MSFT", "NKE", "PG",
    "TRV", "UNH", "V", "VZ", "WMT", "WBA",
]


def _codes_with_any_bar(db) -> set[str]:
    """返回已有至少一条日线的标的代码集合（所有市场）。"""
    rows = db.query(InstrumentDailyBar.etf_code).distinct().all()
    return {code for (code,) in rows}


def _fetch_us_candidates(db, codes_with_data: set[str]) -> list[dict]:
    """从 etf_info 拉所有 active US 标的 + 元数据。"""
    rows = (
        db.query(
            ETFInfo.code,
            ETFInfo.name,
            ETFInfo.exchange,
            ETFInfo.instrument_type,
            ETFInfo.sector,
            ETFInfo.industry,
            ETFInfo.underlying_index,
            ETFInfo.market_cap,
        )
        .filter(ETFInfo.market == "US")
        .filter(ETFInfo.status == "active")
        .order_by(ETFInfo.code.asc())
        .all()
    )

    out = []
    for code, name, exch, itype, sector, industry, underlying, mcap in rows:
        has_data = code in codes_with_data
        bar_count = (
            db.query(func.count(InstrumentDailyBar.trade_date))
            .filter(InstrumentDailyBar.etf_code == code)
            .scalar()
            or 0
        )
        latest_bar_date = (
            db.query(func.max(InstrumentDailyBar.trade_date))
            .filter(InstrumentDailyBar.etf_code == code)
            .scalar()
        )
        out.append(
            {
                "code": code,
                "name": name,
                "exchange": exch,
                "instrument_type": itype,
                "sector": sector,
                "industry": industry,
                "underlying_index": underlying,
                "market_cap": float(mcap) if mcap is not None else None,
                "has_data": has_data,
                "bar_count": int(bar_count),
                "latest_bar_date": latest_bar_date,
            }
        )
    return out


def _assign_tier(row: dict) -> tuple[int, str]:
    """返回 (tier, reason)。tier 数字越小越优先。"""
    code = row["code"]
    itype = row["instrument_type"]
    # 只对「无数据」标的打分；已有数据的默认放到 tier 99（最低）
    if row["has_data"]:
        return (99, "已有数据")

    bare = code.split(".")[0].upper()

    # Tier 1: S&P 500 成分股 = etf_info.instrument_type == 'STOCK'
    if itype == "STOCK":
        return (1, "S&P 500 成分股 (instrument_type=STOCK)")

    # Tier 2: QQQ 重仓（仅限 ETF 标的）
    if itype == "ETF" and bare in QQQ_TOP_HOLDINGS:
        return (2, f"QQQ 重仓 ETF (code={bare})")

    # Tier 3: 道指 30 成分
    if itype == "STOCK" and bare in DOW30_CONSTITUENTS:
        return (3, f"道琼斯 30 成分 ({bare})")

    # Tier 4: 跟踪主要指数的 ETF
    if itype == "ETF":
        ui = (row.get("underlying_index") or "").lower()
        if any(
            kw in ui
            for kw in ["s&p", "dow", "nasdaq", "russell", "total market"]
        ):
            return (4, f"主要指数 ETF (underlying={row.get('underlying_index')})")

    # Tier 5: 其他 ETF
    if itype == "ETF":
        return (5, "其他美股 ETF")

    # Tier 6: 其他 STOCK（理论上不会到这里，因为 Tier 1 已收完 STOCK）
    return (6, "其他美股 STOCK")


def main():
    parser = argparse.ArgumentParser(
        description="生成美股优先级回填清单（CSV + 控制台）"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="输出前 N 条（默认 100）",
    )
    parser.add_argument(
        "--tier",
        type=int,
        default=None,
        help="只看某个 tier（1~6）",
    )
    parser.add_argument(
        "--only-missing",
        action="store_true",
        default=True,
        help="只看无数据的标的（默认开启）",
    )
    parser.add_argument(
        "--include-with-data",
        action="store_true",
        default=False,
        help="包含已有数据的标的（会放在 tier 99）",
    )
    parser.add_argument(
        "--csv",
        default=None,
        help="CSV 输出路径（默认 reports/us_backfill_priority_<YYYY-MM-DD>.csv）",
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="不写 CSV，仅控制台输出",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        print("=" * 70)
        print("US backfill priority report")
        print(f"  date           : {date.today()}")
        print(f"  limit          : {args.limit}")
        print(f"  tier filter    : {args.tier or 'ALL'}")
        print(f"  only-missing   : {args.only_missing and not args.include_with_data}")
        print("=" * 70)

        codes_with_data = _codes_with_any_bar(db)
        rows = _fetch_us_candidates(db, codes_with_data)
        print(f"\n[统计] US active 总数: {len(rows):,}")
        print(f"[统计] 已有数据的标的数: {len(codes_with_data):,}")
        print(f"[统计] 无数据标的数: {sum(1 for r in rows if not r['has_data']):,}")

        # 打分
        for r in rows:
            r["tier"], r["tier_reason"] = _assign_tier(r)

        # 过滤
        if not args.include_with_data:
            rows = [r for r in rows if not r["has_data"]]
        if args.tier is not None:
            rows = [r for r in rows if r["tier"] == args.tier]

        # 排序：tier asc, market_cap desc（大盘优先）
        rows.sort(key=lambda r: (r["tier"], -(r["market_cap"] or 0)))

        # 限制
        limited = rows[: args.limit]

        print(f"\n[输出] {len(limited):,} 行（总候选 {len(rows):,}）")

        # 控制台表格
        if limited:
            header = (
                f"{'Tier':<5} {'Code':<14} {'Type':<7} "
                f"{'MCap(B)':<10} {'Name':<30} Reason"
            )
            print("\n" + header)
            print("-" * len(header))
            for r in limited:
                mcap = (
                    f"{(r['market_cap'] or 0) / 1e9:.1f}"
                    if r["market_cap"]
                    else "-"
                )
                print(
                    f"{r['tier']:<5} {r['code']:<14} "
                    f"{(r['instrument_type'] or '-'):<7} "
                    f"{mcap:<10} {(r['name'] or '')[:28]:<30} "
                    f"{r['tier_reason']}"
                )

        # 写 CSV
        if not args.no_csv:
            csv_path = args.csv or os.path.join(
                "reports",
                f"us_backfill_priority_{date.today().isoformat()}.csv",
            )
            os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
            fieldnames = [
                "tier",
                "tier_reason",
                "code",
                "name",
                "instrument_type",
                "exchange",
                "sector",
                "industry",
                "underlying_index",
                "market_cap",
                "bar_count",
                "latest_bar_date",
                "has_data",
            ]
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                for r in limited:
                    w.writerow({k: r.get(k) for k in fieldnames})
            print(f"\n[CSV] 已写入: {csv_path}")

        # 梯队汇总
        print("\n[汇总] 梯队分布（全量候选，不含 limit 截断）:")
        from collections import Counter

        all_rows = rows  # 截断前的全集
        tier_counts = Counter(r["tier"] for r in all_rows)
        for t in sorted(tier_counts):
            label = {
                1: "S&P 500 成分股",
                2: "QQQ 重仓 ETF",
                3: "道指 30",
                4: "主要指数 ETF",
                5: "其他 ETF",
                6: "其他 STOCK",
                99: "已有数据",
            }.get(t, "?")
            print(f"  Tier {t:>2}: {tier_counts[t]:>4,}  ({label})")

        return 0

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())