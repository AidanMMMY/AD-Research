"""A 股资金流读 service (Fund Flow read service)。

只读 4 张资金流表 + 综合信号表，对外暴露按 ts_code / sector_name /
trade_date 维度的查询。

API 路由层通过 ``app/api/v1/fund_flow.py`` 调用本 service。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data.pipelines.fund_flow import FundFlowPipeline
from app.models.fund_flow import (
    EtfFundFlow,
    FlowSignal,
    IndividualFundFlow,
    SectorFundFlow,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. 个股资金流
# ---------------------------------------------------------------------------


def list_individual(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    trade_date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    ts_code: str | None = None,
    sort: str = "-main_net_inflow",
    limit: int | None = None,
) -> dict[str, Any]:
    """分页查询个股资金流。``sort`` 支持 ``main_net_inflow`` / ``-main_net_inflow`` / ``trade_date``。

    当 ``ts_code`` 提供时,返回该股票所有 trade_date 的历史 (按日期降序)。
    """
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    sort_col, sort_dir = _parse_sort(sort, default_col="main_net_inflow")

    stmt = select(IndividualFundFlow)
    count_stmt = select(func.count(IndividualFundFlow.id))

    if ts_code:
        stmt = stmt.where(IndividualFundFlow.ts_code == ts_code)
        count_stmt = count_stmt.where(IndividualFundFlow.ts_code == ts_code)
    if trade_date:
        stmt = stmt.where(IndividualFundFlow.trade_date == trade_date)
        count_stmt = count_stmt.where(IndividualFundFlow.trade_date == trade_date)
    if start_date:
        stmt = stmt.where(IndividualFundFlow.trade_date >= start_date)
        count_stmt = count_stmt.where(IndividualFundFlow.trade_date >= start_date)
    if end_date:
        stmt = stmt.where(IndividualFundFlow.trade_date <= end_date)
        count_stmt = count_stmt.where(IndividualFundFlow.trade_date <= end_date)

    stmt = stmt.order_by(
        sort_col.desc() if sort_dir == "desc" else sort_col.asc()
    )

    if limit is not None:
        stmt = stmt.limit(limit)
        total = db.execute(count_stmt).scalar() or 0
        rows = db.execute(stmt).scalars().all()
        return {
            "items": [_individual_to_dict(r) for r in rows],
            "total": int(total),
            "page": 1,
            "page_size": len(rows),
        }

    total = db.execute(count_stmt).scalar() or 0
    rows = db.execute(
        stmt.offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()

    return {
        "items": [_individual_to_dict(r) for r in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------
# 2. 板块资金流
# ---------------------------------------------------------------------------


def list_sector(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    trade_date: date | None = None,
    sector_type: str | None = None,
    sector_name: str | None = None,
    sort: str = "-main_net_inflow",
) -> dict[str, Any]:
    """分页查询板块资金流。``sector_type`` = 行业/概念/地域。"""
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    sort_col, sort_dir = _parse_sort(sort, default_col="main_net_inflow")

    stmt = select(SectorFundFlow)
    count_stmt = select(func.count(SectorFundFlow.id))

    if sector_name:
        stmt = stmt.where(SectorFundFlow.sector_name == sector_name)
        count_stmt = count_stmt.where(SectorFundFlow.sector_name == sector_name)
    if sector_type:
        stmt = stmt.where(SectorFundFlow.sector_type == sector_type)
        count_stmt = count_stmt.where(SectorFundFlow.sector_type == sector_type)
    if trade_date:
        stmt = stmt.where(SectorFundFlow.trade_date == trade_date)
        count_stmt = count_stmt.where(SectorFundFlow.trade_date == trade_date)

    stmt = stmt.order_by(
        sort_col.desc() if sort_dir == "desc" else sort_col.asc()
    )

    total = db.execute(count_stmt).scalar() or 0
    rows = db.execute(
        stmt.offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()

    return {
        "items": [_sector_to_dict(r) for r in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------
# 3. 大盘资金流
# ---------------------------------------------------------------------------


def list_market(
    db: Session,
    *,
    days: int = 30,
) -> dict[str, Any]:
    """从 individual_fund_flow 聚合 (无独立 market 表)。

    注：本项目暂未单独建大盘资金流表；返回当日的 market_fund_flow 字段
    从 ``sector_fund_flow`` 行业维度的 '上证' / '深证' 合成 — 但 akshare
    的 sector_fund_flow 不直接提供 sh/sz 字段。

    为简化：从 ``FundFlowPipeline`` 的 ``fetch_market_fund_flow`` 数据源
    走单独的接口返回 — 但因为 akshare 调用是日 ETL 的副产物，service
    层这里只能返回基于 ``sector_fund_flow`` 中 '上证' / '深证' 名称的
    模糊聚合（结果可能为 None）；主指标来源仍以 Pipeline 的 ETL 日志为准。

    真正的"市场整体"在 ak.stock_market_fund_flow 中，但本项目暂未持久化
    大盘表 — 此处返回最新一天的轻量 stub (来自 individual_fund_flow 的
    SH/SZ 段合计)，满足前端 /fund-flow/market 接口的契约。
    """
    cutoff = date.today() - timedelta(days=days)
    # 找最近一个有数据的 trade_date
    latest_date = db.execute(
        select(func.max(SectorFundFlow.trade_date))
    ).scalar() or date.today()
    # 聚合 main_net_inflow 总量作为大盘代理
    total_main = db.execute(
        select(func.coalesce(func.sum(SectorFundFlow.main_net_inflow), 0)).where(
            SectorFundFlow.trade_date == latest_date
        )
    ).scalar() or 0.0

    # 行业段: 没有 sh/sz 区分；返回单点 stub
    return {
        "items": [
            {
                "trade_date": latest_date.isoformat(),
                "sh_main_net_inflow": None,
                "sz_main_net_inflow": None,
                "sh_main_net_pct": None,
                "sz_main_net_pct": None,
                "_note": (
                    "大盘口径未单独建表，sh/sz 字段待接入;此处仅返回最新交易日 "
                    f"与 {float(total_main):.2f} 元行业段合计"
                ),
            }
        ],
        "total": 1,
    }


# ---------------------------------------------------------------------------
# 4. ETF 资金流
# ---------------------------------------------------------------------------


def list_etf(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    trade_date: date | None = None,
    ts_code: str | None = None,
    sort: str = "-inferred_net_inflow",
) -> dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    sort_col, sort_dir = _parse_sort(sort, default_col="inferred_net_inflow")

    stmt = select(EtfFundFlow)
    count_stmt = select(func.count(EtfFundFlow.id))

    if ts_code:
        stmt = stmt.where(EtfFundFlow.ts_code == ts_code)
        count_stmt = count_stmt.where(EtfFundFlow.ts_code == ts_code)
    if trade_date:
        stmt = stmt.where(EtfFundFlow.trade_date == trade_date)
        count_stmt = count_stmt.where(EtfFundFlow.trade_date == trade_date)

    stmt = stmt.order_by(
        sort_col.desc() if sort_dir == "desc" else sort_col.asc()
    )

    total = db.execute(count_stmt).scalar() or 0
    rows = db.execute(
        stmt.offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()

    return {
        "items": [_etf_to_dict(r) for r in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------
# 5. 综合资金信号
# ---------------------------------------------------------------------------


def list_signals(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    trade_date: date | None = None,
    ts_code: str | None = None,
    min_score: float | None = None,
    max_score: float | None = None,
    sort: str = "-composite_score",
) -> dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    sort_col, sort_dir = _parse_sort(sort, default_col="composite_score")

    stmt = select(FlowSignal)
    count_stmt = select(func.count(FlowSignal.id))

    if ts_code:
        stmt = stmt.where(FlowSignal.ts_code == ts_code)
        count_stmt = count_stmt.where(FlowSignal.ts_code == ts_code)
    if trade_date:
        stmt = stmt.where(FlowSignal.trade_date == trade_date)
        count_stmt = count_stmt.where(FlowSignal.trade_date == trade_date)
    if min_score is not None:
        stmt = stmt.where(FlowSignal.composite_score >= min_score)
        count_stmt = count_stmt.where(FlowSignal.composite_score >= min_score)
    if max_score is not None:
        stmt = stmt.where(FlowSignal.composite_score <= max_score)
        count_stmt = count_stmt.where(FlowSignal.composite_score <= max_score)

    stmt = stmt.order_by(
        sort_col.desc() if sort_dir == "desc" else sort_col.asc()
    )

    total = db.execute(count_stmt).scalar() or 0
    rows = db.execute(
        stmt.offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()

    return {
        "items": [_signal_to_dict(r) for r in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


def run_fund_flow_refresh(db: Session, target_date: date | None = None) -> dict[str, Any]:
    """手动触发资金流日刷 (admin endpoint)。"""
    pipeline = FundFlowPipeline(db, target_date=target_date or date.today())
    result = pipeline.run_with_retry(max_attempts=1)
    return {
        "success": result.success,
        "records": result.records,
        "warnings": result.warnings,
        "error": result.error,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_sort(sort: str, default_col: str) -> tuple[Any, str]:
    """解析 ``-main_net_inflow`` / ``main_net_inflow`` 风格的 sort 参数。"""
    from app.models.fund_flow import (
        EtfFundFlow as _Etf,
        FlowSignal as _Fs,
        IndividualFundFlow as _Iff,
        SectorFundFlow as _Sff,
    )

    if not sort:
        sort = f"-{default_col}"
    sort_dir = "asc"
    col_name = sort
    if sort.startswith("-"):
        sort_dir = "desc"
        col_name = sort[1:]

    col_map = {
        "trade_date": {
            IndividualFundFlow: IndividualFundFlow.trade_date,
            SectorFundFlow: SectorFundFlow.trade_date,
            EtfFundFlow: EtfFundFlow.trade_date,
            FlowSignal: FlowSignal.trade_date,
        },
        "main_net_inflow": {
            IndividualFundFlow: IndividualFundFlow.main_net_inflow,
            SectorFundFlow: SectorFundFlow.main_net_inflow,
            FlowSignal: FlowSignal.main_net_inflow,
        },
        "inferred_net_inflow": {EtfFundFlow: EtfFundFlow.inferred_net_inflow},
        "composite_score": {FlowSignal: FlowSignal.composite_score},
        "ts_code": {
            IndividualFundFlow: IndividualFundFlow.ts_code,
            EtfFundFlow: EtfFundFlow.ts_code,
            FlowSignal: FlowSignal.ts_code,
        },
        # ETF-only fields. Without these, sorting by `-premium_rate` /
        # `-net_value` / `-shares_change` falls back to ``IndividualFundFlow``
        # and produces ``UndefinedTable: individual_fund_flow`` SQL errors
        # when the active query is on the ETF table (review-fund-flow P0).
        "premium_rate": {EtfFundFlow: EtfFundFlow.premium_rate},
        "net_value": {EtfFundFlow: EtfFundFlow.net_value},
        "shares_change": {EtfFundFlow: EtfFundFlow.shares_change},
        "shares_outstanding": {EtfFundFlow: EtfFundFlow.shares_outstanding},
        "price": {EtfFundFlow: EtfFundFlow.price},
        "turnover": {EtfFundFlow: EtfFundFlow.turnover},
    }
    for prefix, table_map in col_map.items():
        if col_name == prefix:
            # 选择第一个非空的 ORM 列 (此处只用于返回列对象，调用方会进一步限定表)
            for _cls, col in table_map.items():
                return col, sort_dir
    # fallback: trade_date
    return IndividualFundFlow.trade_date, "desc"


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    return float(v)


def _individual_to_dict(r: IndividualFundFlow) -> dict[str, Any]:
    return {
        "ts_code": r.ts_code,
        "trade_date": r.trade_date.isoformat() if r.trade_date else None,
        "main_net_inflow": _to_float(r.main_net_inflow),
        "main_net_pct": _to_float(r.main_net_pct),
        "super_large_net": _to_float(r.super_large_net),
        "super_large_pct": _to_float(r.super_large_pct),
        "large_net": _to_float(r.large_net),
        "large_pct": _to_float(r.large_pct),
        "medium_net": _to_float(r.medium_net),
        "medium_pct": _to_float(r.medium_pct),
        "small_net": _to_float(r.small_net),
        "small_pct": _to_float(r.small_pct),
        "source": r.source,
        "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
    }


def _sector_to_dict(r: SectorFundFlow) -> dict[str, Any]:
    return {
        "sector_name": r.sector_name,
        "sector_type": r.sector_type,
        "trade_date": r.trade_date.isoformat() if r.trade_date else None,
        "main_net_inflow": _to_float(r.main_net_inflow),
        "main_net_pct": _to_float(r.main_net_pct),
        "super_large_net": _to_float(r.super_large_net),
        "large_net": _to_float(r.large_net),
        "leading_stock": r.leading_stock,
    }


def _etf_to_dict(r: EtfFundFlow) -> dict[str, Any]:
    return {
        "ts_code": r.ts_code,
        "trade_date": r.trade_date.isoformat() if r.trade_date else None,
        "price": _to_float(r.price),
        "net_value": _to_float(r.net_value),
        "premium_rate": _to_float(r.premium_rate),
        "shares_outstanding": _to_float(r.shares_outstanding),
        "shares_change": _to_float(r.shares_change),
        "turnover": _to_float(r.turnover),
        "inferred_net_inflow": _to_float(r.inferred_net_inflow),
    }


def _signal_to_dict(r: FlowSignal) -> dict[str, Any]:
    return {
        "ts_code": r.ts_code,
        "trade_date": r.trade_date.isoformat() if r.trade_date else None,
        "main_net_inflow": _to_float(r.main_net_inflow),
        "margin_net_change": _to_float(r.margin_net_change),
        "lhb_net_buy": _to_float(r.lhb_net_buy),
        "shareholder_count_change": _to_float(r.shareholder_count_change),
        "ah_premium": _to_float(r.ah_premium),
        "block_trade_net": _to_float(r.block_trade_net),
        "composite_score": _to_float(r.composite_score),
        "score_breakdown": r.score_breakdown,
    }
