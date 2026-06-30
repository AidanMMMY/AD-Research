"""ETL data health and pipeline status endpoint.

Provides an aggregated view of recent ETL job runs plus per-market
data freshness, for the operations dashboard.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.etf import ETFInfo, InstrumentDailyBar
from app.models.etl import ETLLog
from app.schemas.auth import UserResponse

router = APIRouter()


# Jobs we surface on the operations dashboard. Keep in sync with the
# pipelines registered in app/core/scheduler.py and app/data/pipelines/*.
_TRACKED_JOBS: list[dict[str, str]] = [
    {"name": "a_share_daily_etl", "label": "A股 ETF 日终采集", "market": "a_share"},
    {"name": "a_stock_daily_etl", "label": "A股 个股日终采集", "market": "a_share"},
    {"name": "a_stock_fundamental_etl", "label": "A股 个股估值数据", "market": "a_share"},
    {"name": "a_stock_discovery", "label": "A股 个股发现", "market": "a_share"},
    {"name": "a_stock_financials", "label": "A股 个股财报", "market": "a_share"},
    {"name": "us_daily_etl", "label": "美股日终采集", "market": "us_stock"},
    {"name": "us_historical_backfill", "label": "美股历史回填", "market": "us_stock"},
    {"name": "us_indicator_calculation", "label": "美股指标计算", "market": "us_stock"},
    {"name": "us_etf_discovery", "label": "美股 ETF 发现", "market": "us_stock"},
    {"name": "us_stock_discovery", "label": "美股 个股发现", "market": "us_stock"},
    {"name": "us_stock_enrichment", "label": "美股 个股元数据补全", "market": "us_stock"},
    {"name": "indicator_calculation", "label": "指标批量计算", "market": "a_share"},
    {"name": "score_calculation", "label": "评分日终计算", "market": "a_share"},
    {"name": "signal_generation", "label": "交易信号生成", "market": "a_share"},
    {"name": "paper_trade_auto", "label": "模拟仓自动交易", "market": "a_share"},
    {"name": "paper_trade_market_update", "label": "模拟仓市值更新", "market": "a_share"},
    {"name": "crypto_daily_etl", "label": "加密货币日终采集", "market": "crypto"},
    {"name": "crypto_indicator_calculation", "label": "加密货币指标计算", "market": "crypto"},
    {"name": "etf_market_scan", "label": "全市场 ETF 扫描", "market": "a_share"},
    {"name": "etf_metadata_enrichment", "label": "ETF 元数据补全", "market": "a_share"},
    {"name": "weekly_pool_reports", "label": "池周报生成", "market": "a_share"},
]


def _latest_bar_date(db: Session, market: str) -> str | None:
    """Return the most recent trade_date for the given market bucket."""
    sub = (
        db.query(InstrumentDailyBar.etf_code)
        .join(ETFInfo, ETFInfo.code == InstrumentDailyBar.etf_code)
        .filter(ETFInfo.market == market)
        .subquery()
    )
    row = (
        db.query(func.max(InstrumentDailyBar.trade_date))
        .filter(InstrumentDailyBar.etf_code.in_(sub))
        .first()
    )
    if row and row[0] is not None:
        return row[0].isoformat()
    return None


def _build_task_summary(db: Session) -> list[dict[str, Any]]:
    """Aggregate the most recent ETLLog row for each tracked job."""
    tasks: list[dict[str, Any]] = []

    for entry in _TRACKED_JOBS:
        name = entry["name"]
        last_run: ETLLog | None = (
            db.query(ETLLog)
            .filter(ETLLog.job_name == name)
            .order_by(desc(ETLLog.created_at))
            .first()
        )

        if last_run is None:
            tasks.append(
                {
                    "name": name,
                    "label": entry["label"],
                    "market": entry["market"],
                    "last_run": None,
                    "status": "never_run",
                    "rows_affected": None,
                    "duration_seconds": None,
                    "error": None,
                }
            )
            continue

        status_value = (last_run.status or "unknown").lower()
        # Normalise "running" and "pending" as a distinct bucket for the UI.
        if status_value not in {"success", "failed", "never_run"}:
            status_value = status_value or "unknown"

        duration: float | None = None
        if last_run.start_time and last_run.end_time:
            start = last_run.start_time
            end = last_run.end_time
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            duration = round((end - start).total_seconds(), 2)

        tasks.append(
            {
                "name": name,
                "label": entry["label"],
                "market": entry["market"],
                "last_run": last_run.created_at.isoformat() if last_run.created_at else None,
                "status": status_value,
                "rows_affected": last_run.records_count,
                "duration_seconds": duration,
                "error": last_run.error_msg,
            }
        )

    return tasks


@router.get("/dashboard")
def get_etl_status(
    db: Session = Depends(get_db),
    _user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the operations dashboard payload.

    Shape:
        last_run_at: ISO timestamp of the most recent log entry (or null)
        tasks: list of job summaries (see _build_task_summary)
        data_freshness: {a_share, us_stock, crypto} -> YYYY-MM-DD or null
    """
    tasks = _build_task_summary(db)

    last_runs = [t["last_run"] for t in tasks if t["last_run"]]
    last_run_at = max(last_runs) if last_runs else None

    data_freshness = {
        "a_share": _latest_bar_date(db, "A股"),
        "us_stock": _latest_bar_date(db, "US"),
        "crypto": _latest_bar_date(db, "CRYPTO"),
    }

    # Stale flag: any market whose latest bar is older than 1 trading day.
    today = date.today()
    stale_markets: list[str] = []
    for market_name, freshness in data_freshness.items():
        if not freshness:
            stale_markets.append(market_name)
            continue
        try:
            days_old = (today - date.fromisoformat(freshness)).days
        except ValueError:
            continue
        # Allow weekends (Mon → Sat = 3 days still acceptable as "fresh")
        if days_old > 3:
            stale_markets.append(market_name)

    return {
        "last_run_at": last_run_at,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stale_markets": stale_markets,
        "tasks": tasks,
        "data_freshness": data_freshness,
    }
