"""A 股免费资金流 API 路由 (方案 C)。

公开接口 (与前端 agent 契约一致)：

* ``GET /fund-flow/individual``                 — 个股资金流 (支持 ``ts_code`` / ``date`` / ``days`` / ``sort`` / ``limit``)
* ``GET /fund-flow/individual/{ts_code}``       — 单只股票历史
* ``GET /fund-flow/sector``                     — 板块资金流 (行业/概念/地域)
* ``GET /fund-flow/sector/{sector_name}``       — 单板块历史
* ``GET /fund-flow/market``                     — 大盘整体资金流 (近 N 日)
* ``GET /fund-flow/etf``                        — ETF 资金流
* ``GET /fund-flow/signals``                    — 综合资金信号 (按 composite_score 排序)
* ``GET /fund-flow/signals/{ts_code}``          — 单只股票综合信号历史
* ``POST /fund-flow/refresh``                   — admin-only 手动 ETL 触发
"""

import logging
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.core.database import SessionLocal
from app.core.redis_client import redis_lock
from app.schemas.auth import UserResponse
from app.schemas.fund_flow import (
    EtfFundFlowListResponse,
    FlowSignalListResponse,
    IndividualFundFlowListResponse,
    MarketFundFlowListResponse,
    SectorFundFlowListResponse,
)
from app.services import fund_flow_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/fund-flow",
    tags=["Fund Flow"],
    dependencies=[Depends(get_current_user)],
)


# ---------------------------------------------------------------------------
# 1. 个股资金流
# ---------------------------------------------------------------------------


@router.get("/individual", response_model=IndividualFundFlowListResponse)
def list_individual(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    trade_date: date | None = Query(None, description="指定交易日 (默认: 最新)"),
    start_date: date | None = None,
    end_date: date | None = None,
    sort: str = Query(
        "-main_net_inflow",
        description="排序: main_net_inflow / -main_net_inflow / trade_date / -trade_date",
    ),
    limit: int | None = Query(None, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> IndividualFundFlowListResponse:
    """全市场个股主力资金流排行 (默认按 main_net_inflow 降序)。"""
    return svc.list_individual(
        db,
        page=page,
        page_size=page_size,
        trade_date=trade_date,
        start_date=start_date,
        end_date=end_date,
        sort=sort,
        limit=limit,
    )


@router.get(
    "/individual/{ts_code}",
    response_model=IndividualFundFlowListResponse,
)
def list_individual_history(
    ts_code: str,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> IndividualFundFlowListResponse:
    """单只股票近 N 日资金流历史。"""
    end = date.today()
    start = end - timedelta(days=days)
    return svc.list_individual(
        db,
        page=1,
        page_size=days,
        ts_code=ts_code,
        start_date=start,
        end_date=end,
        sort="-trade_date",
    )


# ---------------------------------------------------------------------------
# 2. 板块资金流
# ---------------------------------------------------------------------------


@router.get("/sector", response_model=SectorFundFlowListResponse)
def list_sector(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    trade_date: date | None = None,
    sector_type: str | None = Query(None, description="行业 / 概念 / 地域"),
    sort: str = Query("-main_net_inflow"),
    db: Session = Depends(get_db),
) -> SectorFundFlowListResponse:
    """板块资金流 (默认按 main_net_inflow 降序)。"""
    return svc.list_sector(
        db,
        page=page,
        page_size=page_size,
        trade_date=trade_date,
        sector_type=sector_type,
        sort=sort,
    )


@router.get(
    "/sector/{sector_name}",
    response_model=SectorFundFlowListResponse,
)
def list_sector_history(
    sector_name: str,
    days: int = Query(30, ge=1, le=365),
    sector_type: str | None = Query(None, description="行业 / 概念 / 地域"),
    db: Session = Depends(get_db),
) -> SectorFundFlowListResponse:
    """单板块近 N 日资金流历史。"""
    end = date.today()
    start = end - timedelta(days=days)
    # 通过 start_date/end_date 过滤 — 复用 list_sector 接口
    from sqlalchemy import func, select

    from app.models.fund_flow import SectorFundFlow

    stmt = select(SectorFundFlow).where(SectorFundFlow.sector_name == sector_name)
    if sector_type:
        stmt = stmt.where(SectorFundFlow.sector_type == sector_type)
    stmt = stmt.where(SectorFundFlow.trade_date >= start, SectorFundFlow.trade_date <= end)
    stmt = stmt.order_by(SectorFundFlow.trade_date.desc())
    rows = db.execute(stmt).scalars().all()
    items = [
        {
            "sector_name": r.sector_name,
            "sector_type": r.sector_type,
            "trade_date": r.trade_date.isoformat() if r.trade_date else None,
            "main_net_inflow": float(r.main_net_inflow) if r.main_net_inflow is not None else None,
            "main_net_pct": float(r.main_net_pct) if r.main_net_pct is not None else None,
            "super_large_net": float(r.super_large_net) if r.super_large_net is not None else None,
            "large_net": float(r.large_net) if r.large_net is not None else None,
            "leading_stock": r.leading_stock,
        }
        for r in rows
    ]
    return {"items": items, "total": len(items), "page": 1, "page_size": len(items)}  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# 3. 大盘资金流
# ---------------------------------------------------------------------------


@router.get("/market", response_model=MarketFundFlowListResponse)
def list_market_fund_flow(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> MarketFundFlowListResponse:
    """大盘整体资金流 (近 N 日)。

    注意：本接口返回的是基于 sector_fund_flow 行业段聚合的近似值；
    真正的 sh/sz 分离口径在 ak.stock_market_fund_flow 但未单独建表。
    """
    return svc.list_market(db, days=days)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# 4. ETF 资金流
# ---------------------------------------------------------------------------


@router.get("/etf", response_model=EtfFundFlowListResponse)
def list_etf_fund_flow(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    trade_date: date | None = None,
    ts_code: str | None = None,
    sort: str = Query("-inferred_net_inflow"),
    db: Session = Depends(get_db),
) -> EtfFundFlowListResponse:
    """ETF 资金流 (折溢价 + 份额变化 + 推算净流入)。"""
    return svc.list_etf(
        db,
        page=page,
        page_size=page_size,
        trade_date=trade_date,
        ts_code=ts_code,
        sort=sort,
    )


# ---------------------------------------------------------------------------
# 5. 综合资金信号
# ---------------------------------------------------------------------------


@router.get("/signals", response_model=FlowSignalListResponse)
def list_flow_signals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    trade_date: date | None = None,
    min_score: float | None = Query(None, ge=-100, le=100),
    max_score: float | None = Query(None, ge=-100, le=100),
    sort: str = Query("-composite_score"),
    db: Session = Depends(get_db),
) -> FlowSignalListResponse:
    """综合资金信号 (按 composite_score 排序，默认降序 = 资金净流入居前)。"""
    return svc.list_signals(
        db,
        page=page,
        page_size=page_size,
        trade_date=trade_date,
        min_score=min_score,
        max_score=max_score,
        sort=sort,
    )


@router.get(
    "/signals/{ts_code}",
    response_model=FlowSignalListResponse,
)
def list_flow_signal_history(
    ts_code: str,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> FlowSignalListResponse:
    """单只股票近 N 日综合资金信号历史。"""
    return svc.list_signals(
        db,
        page=1,
        page_size=days,
        ts_code=ts_code,
        sort="-trade_date",
    )


# ---------------------------------------------------------------------------
# 6. Admin: 手动 ETL 触发
# ---------------------------------------------------------------------------


@router.post("/refresh", status_code=202)
def refresh_fund_flow(
    trade_date: date | None = Query(None, description="指定交易日; None=今日"),
    _admin: UserResponse = Depends(require_admin),
) -> dict[str, Any]:
    """手动触发资金流日刷 (admin only)。"""
    with redis_lock("fund_flow_daily", expire_seconds=3600) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=409,
                detail="Fund-flow refresh already in progress",
            )
        db = SessionLocal()
        try:
            result = svc.run_fund_flow_refresh(db, target_date=trade_date)
            if not result["success"]:
                raise HTTPException(
                    status_code=500,
                    detail=f"Fund-flow refresh failed: {result['error']}",
                )
            return {
                "status": "ok",
                "records": result["records"],
                "warnings": result["warnings"],
            }
        finally:
            db.close()
