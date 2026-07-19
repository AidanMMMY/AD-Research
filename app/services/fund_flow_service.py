"""A 股资金流读 service (Fund Flow read service)。

只读 4 张资金流表 + 综合信号表，对外暴露按 ts_code / sector_name /
trade_date 维度的查询。

API 路由层通过 ``app/api/v1/fund_flow.py`` 调用本 service。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.data.pipelines.fund_flow import FundFlowPipeline
from app.models.fund_flow import (
    EtfFundFlow,
    FlowSignal,
    IndividualFundFlow,
    MarketFundFlow,
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
    market: str | None = None,
    sort: str = "-main_net_inflow",
    limit: int | None = None,
) -> dict[str, Any]:
    """分页查询个股资金流。``sort`` 支持 ``main_net_inflow`` / ``-main_net_inflow`` / ``trade_date``。

    当 ``ts_code`` 提供时,返回该股票所有 trade_date 的历史 (按日期降序)。
    当未指定任何日期参数且未指定个股时，默认取该表最新交易日，保证首屏为当日数据。
    """
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    sort_col, sort_dir = _parse_sort(sort, default_col="main_net_inflow")

    # 未指定日期/个股时，默认使用最新交易日（避免首屏返回全历史）
    if not trade_date and not start_date and not end_date and not ts_code:
        trade_date = _latest_trade_date(db, IndividualFundFlow)

    stmt = select(IndividualFundFlow)
    count_stmt = select(func.count(IndividualFundFlow.id))

    if ts_code:
        stmt = stmt.where(IndividualFundFlow.ts_code == ts_code)
        count_stmt = count_stmt.where(IndividualFundFlow.ts_code == ts_code)
    if market:
        market_filter = _market_filter_for(IndividualFundFlow, market)
        if market_filter is not None:
            stmt = stmt.where(market_filter)
            count_stmt = count_stmt.where(market_filter)
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

    # 未指定交易日时，默认取板块资金流最新交易日
    if not trade_date:
        trade_date = _latest_trade_date(db, SectorFundFlow)

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
    trade_date: date | None = None,
    days: int = 30,
) -> dict[str, Any]:
    """从 ``market_fund_flow`` 读取大盘资金流。

    返回 ``market='ALL'``（沪深整体，来自 akshare）以及派生的
    ``market='SH'`` / ``market='SZ'`` 净流入。
    当未指定 ``trade_date`` 时，取表中最新交易日。
    """
    _ = days  # 保留参数以兼容旧契约；实际按日期查询

    if not trade_date:
        trade_date = _latest_trade_date(db, MarketFundFlow)

    if not trade_date:
        return {"items": [], "total": 0}

    rows = (
        db.execute(
            select(MarketFundFlow).where(MarketFundFlow.trade_date == trade_date)
        )
        .scalars()
        .all()
    )
    by_market: dict[str, MarketFundFlow] = {r.market: r for r in rows}

    # 若 SH/SZ 行缺失，兜底从 individual_fund_flow 聚合（幂等，不写入）
    for suffix, market in ((".SH", "SH"), (".SZ", "SZ")):
        if market not in by_market:
            agg = _aggregate_individual_fund_flow(db, trade_date, suffix)
            if agg:
                by_market[market] = _market_row_from_dict(agg, market, trade_date)

    all_row = by_market.get("ALL")
    sh_row = by_market.get("SH")
    sz_row = by_market.get("SZ")

    return {
        "items": [
            {
                "trade_date": trade_date.isoformat(),
                "sh_main_net_inflow": _to_float(
                    sh_row.main_net_inflow if sh_row else None
                ),
                "sz_main_net_inflow": _to_float(
                    sz_row.main_net_inflow if sz_row else None
                ),
                "sh_main_net_pct": _to_float(
                    sh_row.main_net_pct if sh_row else None
                ),
                "sz_main_net_pct": _to_float(
                    sz_row.main_net_pct if sz_row else None
                ),
                "total_main_net_inflow": _to_float(
                    all_row.main_net_inflow if all_row else None
                ),
                "total_main_net_pct": _to_float(
                    all_row.main_net_pct if all_row else None
                ),
            }
        ],
        "total": 1,
    }


def _aggregate_individual_fund_flow(
    db: Session, trade_date: date, suffix: str
) -> dict[str, Any] | None:
    """按 ts_code 后缀聚合 individual_fund_flow（用于 SH/SZ 兜底）。"""
    stmt = (
        select(
            func.coalesce(func.sum(IndividualFundFlow.main_net_inflow), 0).label(
                "main_net_inflow"
            ),
            func.coalesce(func.sum(IndividualFundFlow.super_large_net), 0).label(
                "super_large_net"
            ),
            func.coalesce(func.sum(IndividualFundFlow.large_net), 0).label(
                "large_net"
            ),
            func.coalesce(func.sum(IndividualFundFlow.medium_net), 0).label(
                "medium_net"
            ),
            func.coalesce(func.sum(IndividualFundFlow.small_net), 0).label(
                "small_net"
            ),
        )
        .where(IndividualFundFlow.trade_date == trade_date)
        .where(IndividualFundFlow.ts_code.endswith(suffix))
    )
    row = db.execute(stmt).one_or_none()
    if row is None:
        return None
    out: dict[str, Any] = {}
    for col in (
        "main_net_inflow",
        "super_large_net",
        "large_net",
        "medium_net",
        "small_net",
    ):
        value = getattr(row, col)
        out[col] = float(value) if value is not None else None
    if all(v is None or v == 0 for v in out.values()):
        return None
    return out


def _market_row_from_dict(
    data: dict[str, Any], market: str, trade_date: date
) -> MarketFundFlow:
    """从聚合字典构造一个只读 ``MarketFundFlow`` 实例（不写入 DB）。"""
    return MarketFundFlow(
        trade_date=trade_date,
        market=market,
        main_net_inflow=data.get("main_net_inflow"),
        super_large_net=data.get("super_large_net"),
        large_net=data.get("large_net"),
        medium_net=data.get("medium_net"),
        small_net=data.get("small_net"),
    )


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

    # 未指定日期/ETF 时，默认取 ETF 资金流最新交易日
    if not trade_date and not ts_code:
        trade_date = _latest_trade_date(db, EtfFundFlow)

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

    # 未指定日期/个股时，默认取综合信号最新交易日
    if not trade_date and not ts_code:
        trade_date = _latest_trade_date(db, FlowSignal)

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


def _latest_trade_date(db: Session, model: type) -> date | None:
    """获取指定资金流表最新交易日；无数据时返回 None。"""
    return db.execute(select(func.max(model.trade_date))).scalar()


def _market_filter_for(model: type[IndividualFundFlow], market: str) -> Any | None:
    """根据市场/板块标签生成 ts_code 过滤条件；不支持的标签返回 None。

    支持中文标签与短代码：
    - SH / 沪市      -> 后缀 .SH
    - SZ / 深市      -> 后缀 .SZ
    - CYB / 创业板   -> 前缀 300 / 301
    - KCB / 科创板   -> 前缀 688
    - BJ / 北交所    -> 前缀 8 / 43 / 83 / 87
    """
    # 后缀匹配：沪市 / 深市
    suffix_map = {
        "SH": ".SH",
        "沪市": ".SH",
        "SZ": ".SZ",
        "深市": ".SZ",
    }
    # 前缀匹配：创业板 / 科创板 / 北交所
    prefix_map = {
        "CYB": ["300", "301"],
        "创业板": ["300", "301"],
        "KCB": ["688"],
        "科创板": ["688"],
        "BJ": ["8", "43", "83", "87"],
        "北交所": ["8", "43", "83", "87"],
    }
    if market in suffix_map:
        return model.ts_code.endswith(suffix_map[market])
    if market in prefix_map:
        return or_(*[model.ts_code.startswith(p) for p in prefix_map[market]])
    return None


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
        "id": r.id,
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
        "id": r.id,
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
        "id": r.id,
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
        "id": r.id,
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
