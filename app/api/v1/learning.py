"""学习中心 API routes（方案 B MVP，2026-08-02）。

把"深度分析 / 科普教育"类资讯从快讯 feed 里捞出来，供前端
``/learning`` 学习中心的知识 feed 区使用：

* ``GET /learning/feed``   — 按主题/内容类型过滤的知识文章流
* ``GET /learning/topics`` — 各主题近 N 天文章计数（Tab 徽标）

数据路径：``news_article`` JOIN ``news_source_meta``（按 source），
只返回源已打标（deep/edu）且近 ``days`` 天的文章——不改
``news_article`` 结构、不回填历史数据。列表项序列化复用
``app.api.v1.news._article_to_dict``（与 /news 列表项结构一致），
另附 ``content_type`` / ``topic`` / ``importance`` / ``difficulty_default``
四个学习维度字段。排序为 importance DESC NULLS LAST +
published_at DESC（知识内容半衰期长，重要性优先于纯时间倒序）。

打标数据来自 ``app.services.news.source_meta_seed``（静态映射，
``scripts/seed_news_source_meta.py`` 灌库）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.api.v1.news import _article_to_dict
from app.models.news_source_meta import CONTENT_TYPES, TOPICS, NewsSourceMeta
from app.services.news._model_loader import NewsArticle

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["learning"],
    dependencies=[Depends(get_current_user)],
)

#: days 参数上限——知识 feed 只看近期数据，窗口过大会拖慢 join。
_MAX_DAYS = 365


def _learning_item(article: NewsArticle, meta: NewsSourceMeta) -> dict:
    """在 /news 列表项结构之上附加学习维度字段。"""
    item = _article_to_dict(article)
    item["importance"] = article.importance
    item["content_type"] = meta.content_type
    item["topic"] = meta.topic
    item["difficulty_default"] = meta.difficulty_default
    return item


@router.get("/feed")
def learning_feed(
    topic: str | None = Query(
        None,
        description=(
            "按主题过滤。Allowed: allocation | valuation | macro | "
            "industry | psychology | tools | research"
        ),
    ),
    content_type: str | None = Query(
        None, description="按内容类型过滤。Allowed: deep | edu"
    ),
    days: int = Query(
        90, ge=1, le=_MAX_DAYS, description="回看窗口（天），默认 90"
    ),
    page: int = Query(1, ge=1, description="1-indexed page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size (1-100)"),
    db: Session = Depends(get_db),
) -> dict:
    """知识文章流：只含已打标源、近 ``days`` 天的文章。

    排序 importance DESC NULLS LAST, published_at DESC；响应结构与
    ``GET /news`` 一致（items/page/page_size/total/total_pages）。
    """
    if topic is not None and topic not in TOPICS:
        raise HTTPException(
            status_code=400,
            detail=f"topic must be one of {', '.join(TOPICS)}",
        )
    if content_type is not None and content_type not in CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"content_type must be one of {', '.join(CONTENT_TYPES)}",
        )

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    # published_at 是 naive UTC（crawler 入库前统一转 UTC 后去时区），
    # 比较时同样用 naive 值。
    cutoff_naive = cutoff.replace(tzinfo=None)

    join_cond = NewsArticle.source == NewsSourceMeta.source
    stmt = (
        select(NewsArticle, NewsSourceMeta)
        .join(NewsSourceMeta, join_cond)
        .where(NewsArticle.published_at >= cutoff_naive)
    )
    count_stmt = (
        select(func.count(NewsArticle.id))
        .join(NewsSourceMeta, join_cond)
        .where(NewsArticle.published_at >= cutoff_naive)
    )
    if topic is not None:
        stmt = stmt.where(NewsSourceMeta.topic == topic)
        count_stmt = count_stmt.where(NewsSourceMeta.topic == topic)
    if content_type is not None:
        stmt = stmt.where(NewsSourceMeta.content_type == content_type)
        count_stmt = count_stmt.where(NewsSourceMeta.content_type == content_type)

    total = db.execute(count_stmt).scalar() or 0
    rows = db.execute(
        stmt.order_by(
            NewsArticle.importance.desc().nulls_last(),
            NewsArticle.published_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = [_learning_item(article, meta) for article, meta in rows]
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": int(total),
        "total_pages": (int(total) + page_size - 1) // page_size if total else 0,
        "days": days,
    }


@router.get("/topics")
def learning_topics(
    days: int = Query(
        90, ge=1, le=_MAX_DAYS, description="回看窗口（天），默认 90"
    ),
    db: Session = Depends(get_db),
) -> dict:
    """各主题近 ``days`` 天的文章计数，供前端主题 Tab 显示徽标。

    返回全部 7 个主题（含 research 兜底类），无文章的主题计数为 0，
    保证前端 Tab 列表稳定。
    """
    cutoff_naive = (datetime.now(tz=timezone.utc) - timedelta(days=days)).replace(
        tzinfo=None
    )
    rows = db.execute(
        select(NewsSourceMeta.topic, func.count(NewsArticle.id))
        .join(NewsSourceMeta, NewsArticle.source == NewsSourceMeta.source)
        .where(NewsArticle.published_at >= cutoff_naive)
        .group_by(NewsSourceMeta.topic)
    ).all()
    counts = {topic: int(n) for topic, n in rows if topic is not None}
    return {
        "days": days,
        "topics": [
            {"topic": topic, "count": counts.get(topic, 0)} for topic in TOPICS
        ],
        "total": sum(counts.values()),
    }
