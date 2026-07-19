#!/usr/bin/env python3
"""ETL / 数据新鲜度监控脚本。

检查各市场最新日线日期、各 ETL job 最近成功时间、以及当前卡死的
running 任务。用于 CI、健康检查、日常巡检。

环境变量:
    DATABASE_URL: PostgreSQL 连接字符串
    REDIS_URL:    Redis 连接字符串（可选；未设置时跳过锁检查）

用法:
    python scripts/audit_etl_freshness.py
    python scripts/audit_etl_freshness.py --a-share-threshold 1 --us-threshold 1 --crypto-threshold 1

退出码:
    0  OK
    1  WARN 或 CRITICAL
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


THRESHOLD_OK = "OK"
THRESHOLD_WARN = "WARN"
THRESHOLD_CRITICAL = "CRITICAL"


class CheckResult:
    """Single check result."""

    def __init__(
        self,
        name: str,
        status: str,
        message: str,
        detail: dict | None = None,
    ):
        self.name = name
        self.status = status
        self.message = message
        self.detail = detail or {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_date(val) -> date | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    return None


def check_market_freshness(
    engine: Engine,
    market: str,
    threshold_days: int,
) -> CheckResult:
    """检查某市场 ``instrument_daily_bar`` 最新交易日是否落后。"""
    sql = text(
        """
        SELECT MAX(b.trade_date) AS latest_date
        FROM instrument_daily_bar b
        JOIN etf_info i ON i.code = b.etf_code
        WHERE i.market = :market
        """
    )
    with engine.connect() as conn:
        row = conn.execute(sql, {"market": market}).fetchone()
    latest = _parse_date(row[0]) if row else None

    if latest is None:
        return CheckResult(
            name=f"freshness_{market}",
            status=THRESHOLD_CRITICAL,
            message=f"{market} 无日线数据",
        )

    today = _now().date()
    lag = (today - latest).days

    if lag <= threshold_days:
        status = THRESHOLD_OK
    elif lag <= threshold_days + 1:
        status = THRESHOLD_WARN
    else:
        status = THRESHOLD_CRITICAL

    return CheckResult(
        name=f"freshness_{market}",
        status=status,
        message=f"{market} 最新日线 {latest}，落后 {lag} 天",
        detail={"latest_date": latest.isoformat(), "lag_days": lag},
    )


def check_etl_success(
    engine: Engine,
    job_name: str,
    threshold_hours: int,
) -> CheckResult:
    """检查某个 ETL job 最近一次成功时间。"""
    sql = text(
        """
        SELECT MAX(end_time) AS latest_end
        FROM etl_log
        WHERE job_name = :job_name AND status = 'success'
        """
    )
    with engine.connect() as conn:
        row = conn.execute(sql, {"job_name": job_name}).fetchone()
    latest = row[0]

    if latest is None:
        return CheckResult(
            name=f"etl_success_{job_name}",
            status=THRESHOLD_CRITICAL,
            message=f"ETL {job_name} 无成功记录",
        )

    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    hours = (_now() - latest).total_seconds() / 3600

    if hours <= threshold_hours:
        status = THRESHOLD_OK
    elif hours <= threshold_hours * 2:
        status = THRESHOLD_WARN
    else:
        status = THRESHOLD_CRITICAL

    return CheckResult(
        name=f"etl_success_{job_name}",
        status=status,
        message=f"ETL {job_name} 最近成功 {latest.isoformat()}，距今 {hours:.1f} 小时",
        detail={"latest_success": latest.isoformat(), "hours_since": hours},
    )


def check_stuck_etl(engine: Engine, threshold_minutes: int = 120) -> CheckResult:
    """检查 ``etl_log`` 中 status='running' 且超时的任务。"""
    cutoff = _now() - timedelta(minutes=threshold_minutes)
    sql = text(
        """
        SELECT job_name, start_time
        FROM etl_log
        WHERE status = 'running'
          AND start_time < :cutoff
        ORDER BY start_time ASC
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"cutoff": cutoff}).fetchall()

    if not rows:
        return CheckResult(
            name="stuck_etl",
            status=THRESHOLD_OK,
            message="无卡死的 ETL 任务",
            detail={"count": 0},
        )

    # Mark as CRITICAL if any stuck job exists; WARN if we are lenient.
    status = THRESHOLD_CRITICAL
    jobs = [f"{r[0]} (since {r[1]})" for r in rows]
    return CheckResult(
        name="stuck_etl",
        status=status,
        message=f"发现 {len(rows)} 个卡死的 ETL 任务",
        detail={"count": len(rows), "jobs": jobs},
    )


def check_redis_locks() -> CheckResult | None:
    """可选：检查 Redis 中是否存在长期未释放的调度器锁。"""
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        return None
    try:
        from app.core.redis_client import get_redis_client

        client = get_redis_client()
        # Look for lock:* keys older than 2 hours
        lock_keys = [k for k in client.scan_iter(match="lock:*")]
        stale = []
        now = _now().timestamp()
        for key in lock_keys:
            ttl = client.ttl(key)
            # A lock with no TTL or very long TTL is suspicious
            if ttl == -1 or ttl > 7200:
                stale.append(key)
        if stale:
            return CheckResult(
                name="redis_locks",
                status=THRESHOLD_WARN,
                message=f"Redis 中存在 {len(stale)} 个可疑锁",
                detail={"keys": stale[:20]},
            )
        return CheckResult(
            name="redis_locks",
            status=THRESHOLD_OK,
            message="Redis 锁状态正常",
            detail={"count": len(lock_keys)},
        )
    except Exception as exc:
        return CheckResult(
            name="redis_locks",
            status=THRESHOLD_WARN,
            message=f"Redis 锁检查失败: {exc}",
        )


def run_all_checks(args: argparse.Namespace) -> list[CheckResult]:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("错误: 请设置 DATABASE_URL 环境变量", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(database_url)
    results: list[CheckResult] = []

    # Market freshness
    for market, threshold in [
        ("A股", args.a_share_threshold),
        ("US", args.us_threshold),
        ("CRYPTO", args.crypto_threshold),
    ]:
        results.append(check_market_freshness(engine, market, threshold))

    # ETL success for key jobs
    etl_jobs = [
        ("a_share_daily_etl", args.etl_threshold_hours),
        ("a_stock_daily_etl", args.etl_threshold_hours),
        ("us_daily_etl", args.etl_threshold_hours),
        ("crypto_daily_etl", args.etl_threshold_hours),
        ("indicator_calc", args.etl_threshold_hours * 2),
        ("score_calculation", args.etl_threshold_hours * 2),
    ]
    for job, threshold in etl_jobs:
        results.append(check_etl_success(engine, job, threshold))

    # Stuck ETL
    results.append(check_stuck_etl(engine, args.stuck_threshold_minutes))

    # Redis locks (optional)
    redis_result = check_redis_locks()
    if redis_result:
        results.append(redis_result)

    return results


def print_report(results: list[CheckResult]) -> int:
    sep = "=" * 70
    print(sep)
    print("ETL / 数据新鲜度监控")
    print(sep)

    worst = THRESHOLD_OK
    for r in results:
        print(f"[{r.status:8}] {r.name}: {r.message}")
        if r.status == THRESHOLD_CRITICAL:
            worst = THRESHOLD_CRITICAL
        elif r.status == THRESHOLD_WARN and worst == THRESHOLD_OK:
            worst = THRESHOLD_WARN

    print(sep)
    print(f"总体状态: {worst}")
    print(sep)
    return 0 if worst == THRESHOLD_OK else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ETL 与数据新鲜度监控")
    parser.add_argument(
        "--a-share-threshold",
        type=int,
        default=1,
        help="A 股日线落后阈值（交易日），默认 1",
    )
    parser.add_argument(
        "--us-threshold",
        type=int,
        default=1,
        help="美股日线落后阈值（交易日），默认 1",
    )
    parser.add_argument(
        "--crypto-threshold",
        type=int,
        default=2,
        help="Crypto 日线落后阈值（自然日），默认 2",
    )
    parser.add_argument(
        "--etl-threshold-hours",
        type=int,
        default=25,
        help="ETL 成功间隔阈值（小时），默认 25",
    )
    parser.add_argument(
        "--stuck-threshold-minutes",
        type=int,
        default=120,
        help="ETL 卡死阈值（分钟），默认 120",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = run_all_checks(args)
    return print_report(results)


if __name__ == "__main__":
    sys.exit(main())
