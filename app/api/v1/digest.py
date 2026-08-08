"""每日 AI 综合研报 API（Daily Digest，2026-08-03，B5）。

路由前缀 ``/digest``（main.py 挂载 ``/api/v1/digest``）：

- ``GET /digest``                 分页列表（不含 content_md），report_date 倒序
- ``GET /digest/latest``          最新一篇全文（含 content_md / sections_json /
                                  data_snapshot_json / llm_model）；无记录 404
- ``GET /digest/latest/summary``  Dashboard 轻量摘要；无记录 404
- ``GET /digest/{id}``            按 id 全文；无记录 404
- ``GET /digest/by-date/{date}``  指定日全文；日期格式非法 400，无记录 404
- ``POST /digest/regenerate``     admin 限定，后台线程异步重生成，立即返回

404 语义 = 空态而非错误（前端契约，见 web/src/api/digest.ts）。
鉴权对齐 reports.py：router 级 ``get_current_user``；regenerate 额外
``require_admin``。
"""

import logging
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.core.scheduler import run_daily_digest
from app.models.digest import DailyDigest
from app.schemas.auth import UserResponse
from app.schemas.digest import (
    DigestDetail,
    DigestListItem,
    DigestListResponse,
    DigestRegenerateRequest,
    DigestRegenerateResponse,
    DigestSummary,
)
from app.services.digest.collector import SHANGHAI

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


# ------------------------------------------------------------------
# 序列化辅助（content_chars / sections_json 空值兜底，对齐前端契约）
# ------------------------------------------------------------------

def _content_chars(digest: DailyDigest) -> int:
    return len(digest.content_md or "")


def _to_list_item(digest: DailyDigest) -> DigestListItem:
    return DigestListItem(
        id=digest.id,
        report_date=digest.report_date,
        status=digest.status,
        title=digest.title or "",
        summary_md=digest.summary_md,
        content_chars=_content_chars(digest),
        created_at=digest.created_at,
    )


def _to_detail(digest: DailyDigest) -> DigestDetail:
    return DigestDetail(
        id=digest.id,
        report_date=digest.report_date,
        status=digest.status,
        title=digest.title or "",
        summary_md=digest.summary_md,
        content_md=digest.content_md,
        # 前端按数组渲染，None → [] 兜底
        sections_json=digest.sections_json or [],
        data_snapshot_json=digest.data_snapshot_json,
        llm_model=digest.llm_model,
        error_msg=digest.error_msg,
        report_metadata_id=digest.report_metadata_id,
        started_at=digest.started_at,
        finished_at=digest.finished_at,
        created_at=digest.created_at,
    )


def _get_latest(db: Session) -> DailyDigest | None:
    return (
        db.execute(
            select(DailyDigest).order_by(DailyDigest.report_date.desc()).limit(1)
        )
        .scalars()
        .first()
    )


# ------------------------------------------------------------------
# 列表 / 详情
# ------------------------------------------------------------------

@router.get("", response_model=DigestListResponse)
def list_digests(
    page: int = Query(1, ge=1, description="1-indexed page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size (1-100)"),
    db: Session = Depends(get_db),
):
    """分页列出历史研报（report_date 倒序，不含 content_md 全文）。"""
    total = db.scalar(select(func.count()).select_from(DailyDigest)) or 0
    rows = (
        db.execute(
            select(DailyDigest)
            .order_by(DailyDigest.report_date.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return DigestListResponse(
        items=[_to_list_item(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total else 0,
    )


@router.get("/latest", response_model=DigestDetail)
def get_latest_digest(db: Session = Depends(get_db)):
    """最新一篇完整研报；一篇都没有时 404（前端据此走空态）。"""
    digest = _get_latest(db)
    if digest is None:
        raise HTTPException(status_code=404, detail="暂无每日研报")
    return _to_detail(digest)


@router.get("/latest/summary", response_model=DigestSummary)
def get_latest_digest_summary(db: Session = Depends(get_db)):
    """Dashboard 摘要卡：只回 5 个轻量字段；无记录 404。"""
    digest = _get_latest(db)
    if digest is None:
        raise HTTPException(status_code=404, detail="暂无每日研报")
    return DigestSummary(
        id=digest.id,
        report_date=digest.report_date,
        status=digest.status,
        title=digest.title or "",
        summary_md=digest.summary_md,
        content_chars=_content_chars(digest),
    )


@router.get("/by-date/{date_str}", response_model=DigestDetail)
def get_digest_by_date(date_str: str, db: Session = Depends(get_db)):
    """按报告日期取全文；日期格式须为 YYYY-MM-DD，非法 400，无记录 404。"""
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400, detail="日期格式非法，应为 YYYY-MM-DD"
        ) from None
    digest = (
        db.execute(select(DailyDigest).where(DailyDigest.report_date == target))
        .scalars()
        .first()
    )
    if digest is None:
        raise HTTPException(
            status_code=404, detail=f"{date_str} 无每日研报"
        )
    return _to_detail(digest)


# ------------------------------------------------------------------
# 手动重生成（admin）
# ------------------------------------------------------------------

@router.post("/regenerate", response_model=DigestRegenerateResponse, status_code=202)
def regenerate_digest(
    request: DigestRegenerateRequest | None = None,
    _: UserResponse = Depends(require_admin),
):
    """后台线程异步重生成指定日（默认今天 Asia/Shanghai）的研报。

    直接复用调度入口 ``run_daily_digest``——同一把
    ``redis_lock("daily_digest")`` + ETLLog 记录，与 06:30 定时跑
    行为完全一致；与定时任务撞车时后到会拿锁失败静默跳过。
    立即返回 202 + report_date，前端自行轮询 /digest/by-date。
    """
    target = (
        request.target_date
        if request and request.target_date
        else datetime.now(SHANGHAI).date()
    )
    threading.Thread(
        target=run_daily_digest,
        kwargs={"target_date": target},
        daemon=True,
        name=f"daily-digest-regen-{target.isoformat()}",
    ).start()
    logger.info("digest regenerate accepted: report_date=%s", target)
    return DigestRegenerateResponse(status="accepted", report_date=target)


# ------------------------------------------------------------------
# 按 id 详情（放最后，避免抢占 /latest、/by-date 等静态段）
# ------------------------------------------------------------------

@router.get("/{digest_id}", response_model=DigestDetail)
def get_digest_by_id(digest_id: int, db: Session = Depends(get_db)):
    """按 id 取完整研报；无记录 404。"""
    digest = db.get(DailyDigest, digest_id)
    if digest is None:
        raise HTTPException(
            status_code=404, detail=f"Digest {digest_id} not found"
        )
    return _to_detail(digest)
