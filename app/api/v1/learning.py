"""学习中心 API routes（方案 B MVP，2026-08-02；P1 收藏/已读 2026-08-02）。

把"深度分析 / 科普教育"类资讯从快讯 feed 里捞出来，供前端
``/learning`` 学习中心的知识 feed 区使用：

* ``GET /learning/feed``   — 按主题/内容类型过滤的知识文章流
  （P1 起每项附当前用户的 ``bookmarked`` / ``read`` 布尔）
* ``GET /learning/topics`` — 各主题近 N 天文章计数（Tab 徽标）
* ``POST /learning/articles/{id}/bookmark`` — 收藏切换（幂等：再调取消）
* ``POST /learning/articles/{id}/read``     — 标记已读（幂等）
* ``GET /learning/bookmarks`` — 我的收藏列表（稍后读）

数据路径：``news_article`` JOIN ``news_source_meta``（按 source），
只返回源已打标（deep/edu）且近 ``days`` 天的文章——不改
``news_article`` 结构、不回填历史数据。列表项序列化复用
``app.api.v1.news._article_to_dict``（与 /news 列表项结构一致），
另附 ``content_type`` / ``topic`` / ``importance`` / ``difficulty_default``
四个学习维度字段。排序为 importance DESC NULLS LAST +
published_at DESC（知识内容半衰期长，重要性优先于纯时间倒序）。

收藏/已读状态存 ``user_article_state``（(user_id, article_id) 复合
PK，见 ``app.models.user_article_state``）：feed 用 LEFT JOIN 把
当前用户状态折成布尔；收藏列表按 bookmarked_at DESC。取消收藏
置 NULL 不删行，已读标记得以保留。

打标数据来自 ``app.services.news.source_meta_seed``（静态映射，
``scripts/seed_news_source_meta.py`` 灌库）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.api.v1.news import _article_to_dict, _iso_utc
from app.models.news_source_meta import (
    CONTENT_TYPES,
    DIFFICULTIES,
    TOPICS,
    NewsSourceMeta,
)
from app.models.user_article_state import UserArticleState
from app.schemas.auth import UserResponse
from app.services.news._model_loader import NewsArticle

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["learning"],
    dependencies=[Depends(get_current_user)],
)

#: days 参数上限——知识 feed 只看近期数据，窗口过大会拖慢 join。
_MAX_DAYS = 365


def _learning_item(
    article: NewsArticle,
    meta: NewsSourceMeta | None,
    state: UserArticleState | None = None,
) -> dict:
    """在 /news 列表项结构之上附加学习维度字段 + 用户状态布尔。

    ``meta`` 可空：收藏列表允许收藏未打标源的文章（用户在 /news 也
    可能点收藏——虽然当前只有学习中心暴露按钮，API 不限制来源）。
    ``state`` 是当前用户的 user_article_state 行（无行为 None）。
    """
    item = _article_to_dict(article)
    item["importance"] = article.importance
    item["content_type"] = meta.content_type if meta else None
    item["topic"] = meta.topic if meta else None
    item["difficulty_default"] = meta.difficulty_default if meta else None
    # P1：当前用户的收藏/已读布尔（feed / 收藏列表都带）
    item["bookmarked"] = state is not None and state.bookmarked_at is not None
    item["read"] = state is not None and state.read_at is not None
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
    difficulty: str | None = Query(
        None,
        description=(
            "按源级默认难度过滤（P2, 2026-08-02）。"
            "Allowed: beginner | advanced"
        ),
    ),
    days: int = Query(
        90, ge=1, le=_MAX_DAYS, description="回看窗口（天），默认 90"
    ),
    page: int = Query(1, ge=1, description="1-indexed page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size (1-100)"),
    db: Session = Depends(get_db),
    user: UserResponse = Depends(get_current_user),
) -> dict:
    """知识文章流：只含已打标源、近 ``days`` 天的文章。

    排序 importance DESC NULLS LAST, published_at DESC；响应结构与
    ``GET /news`` 一致（items/page/page_size/total/total_pages）。
    P1 起每项附当前用户的 ``bookmarked`` / ``read`` 布尔（LEFT JOIN
    ``user_article_state``，无状态行时为 false）。
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
    if difficulty is not None and difficulty not in DIFFICULTIES:
        raise HTTPException(
            status_code=400,
            detail=f"difficulty must be one of {', '.join(DIFFICULTIES)}",
        )

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    # published_at 是 naive UTC（crawler 入库前统一转 UTC 后去时区），
    # 比较时同样用 naive 值。
    cutoff_naive = cutoff.replace(tzinfo=None)

    join_cond = NewsArticle.source == NewsSourceMeta.source
    # P1：LEFT JOIN 当前用户的状态行（收藏/已读布尔）。复合主键前导列
    # 是 user_id，故 (article_id, user_id) 等值 join 走
    # ix_user_article_state_article_id + 主键，不会全表扫。
    state_join = and_(
        UserArticleState.article_id == NewsArticle.id,
        UserArticleState.user_id == user.id,
    )
    stmt = (
        select(NewsArticle, NewsSourceMeta, UserArticleState)
        .join(NewsSourceMeta, join_cond)
        .outerjoin(UserArticleState, state_join)
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
    if difficulty is not None:
        stmt = stmt.where(NewsSourceMeta.difficulty_default == difficulty)
        count_stmt = count_stmt.where(
            NewsSourceMeta.difficulty_default == difficulty
        )

    total = db.execute(count_stmt).scalar() or 0
    rows = db.execute(
        stmt.order_by(
            NewsArticle.importance.desc().nulls_last(),
            NewsArticle.published_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = [
        _learning_item(article, meta, state) for article, meta, state in rows
    ]
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


# ---------------------------------------------------------------------------
# P1：文章级收藏（稍后读）+ 已读标记
# ---------------------------------------------------------------------------


def _get_or_create_state(
    db: Session, *, user_id: int, article_id: int
) -> UserArticleState:
    """取 (user, article) 状态行，不存在则新建（两时间戳均为 NULL）。

    调用方负责 commit。文章不存在抛 404——收藏/已读一篇不存在的
    文章几乎没有意义，且能让前端尽早发现脏 id。
    """
    if db.get(NewsArticle, article_id) is None:
        raise HTTPException(status_code=404, detail="article not found")
    state = db.get(UserArticleState, (user_id, article_id))
    if state is None:
        state = UserArticleState(user_id=user_id, article_id=article_id)
        db.add(state)
    return state


@router.post("/articles/{article_id}/bookmark")
def toggle_bookmark(
    article_id: int,
    db: Session = Depends(get_db),
    user: UserResponse = Depends(get_current_user),
) -> dict:
    """收藏切换（稍后读）：未收藏→收藏，已收藏→取消。

    幂等语义在"状态"而非"调用次数"上——响应里的 ``bookmarked``
    永远等于调用后的真实状态，前端乐观更新失败重试不会产生
    幽灵状态。取消收藏只把 ``bookmarked_at`` 置 NULL 不删行，
    已读标记（``read_at``）得以保留。
    """
    state = _get_or_create_state(db, user_id=user.id, article_id=article_id)
    if state.bookmarked_at is None:
        state.bookmarked_at = datetime.now(tz=timezone.utc)
    else:
        state.bookmarked_at = None
    db.commit()
    return {
        "article_id": article_id,
        "bookmarked": state.bookmarked_at is not None,
        "bookmarked_at": _iso_utc(state.bookmarked_at),
    }


@router.post("/articles/{article_id}/read")
def mark_read(
    article_id: int,
    db: Session = Depends(get_db),
    user: UserResponse = Depends(get_current_user),
) -> dict:
    """标记已读（幂等）：首次写入 ``read_at``，重复调用不改写原时间戳。

    "首次阅读时间"对后续阅读行为分析有用，所以重复标记是 no-op
    而非刷新时间。
    """
    state = _get_or_create_state(db, user_id=user.id, article_id=article_id)
    if state.read_at is None:
        state.read_at = datetime.now(tz=timezone.utc)
        db.commit()
    return {
        "article_id": article_id,
        "read": True,
        "read_at": _iso_utc(state.read_at),
    }


@router.get("/bookmarks")
def list_bookmarks(
    page: int = Query(1, ge=1, description="1-indexed page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size (1-100)"),
    db: Session = Depends(get_db),
    user: UserResponse = Depends(get_current_user),
) -> dict:
    """我的收藏列表（稍后读）：只含当前用户 bookmarked_at 非空的文章。

    按 bookmarked_at DESC（最近收藏在最前）。序列化复用 feed 的
    ``_learning_item``；收藏不限于打标源的文章，所以 source_meta
    用 OUTER JOIN（未打标源的文章 content_type/topic 为 null）。
    """
    base = (
        select(NewsArticle, NewsSourceMeta, UserArticleState)
        .join(
            UserArticleState,
            and_(
                UserArticleState.article_id == NewsArticle.id,
                UserArticleState.user_id == user.id,
                UserArticleState.bookmarked_at.is_not(None),
            ),
        )
        .outerjoin(
            NewsSourceMeta, NewsArticle.source == NewsSourceMeta.source
        )
    )
    count_stmt = select(func.count()).select_from(
        select(UserArticleState.article_id)
        .where(
            UserArticleState.user_id == user.id,
            UserArticleState.bookmarked_at.is_not(None),
        )
        .subquery()
    )
    total = db.execute(count_stmt).scalar() or 0
    rows = db.execute(
        base.order_by(UserArticleState.bookmarked_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = [
        _learning_item(article, meta, state) for article, meta, state in rows
    ]
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": int(total),
        "total_pages": (int(total) + page_size - 1) // page_size if total else 0,
    }
