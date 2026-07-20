"""News API routes.

Exposes the ``news_article`` and ``news_article_symbol`` tables for
frontend consumers:

* ``GET  /news``                          — list + filter + paginate
* ``GET  /news/watchlist``                — list scoped to the user's favorites
* ``GET  /news/{article_id}``             — detail + linked symbols
* ``GET  /news/stats/sources``            — per-source ingestion volume (last 7d)
* ``GET  /news/health``                   — per-source diagnostics + scheduler status
* ``POST /news/{article_id}/fetch-content``  — Jina Reader full-text fetch
* ``POST /news/{article_id}/translate``   — DeepSeek translate (en → zh), cached

All routes require a valid JWT. Crawler / scheduler backends hit the
DB directly via :mod:`app.services.news.normalizer` — these endpoints
are read-only (apart from the two POSTs above, which only fill derived
cache columns).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import redis
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config import get_settings
from app.core.redis_client import get_redis_client, redis_lock
from app.core.scheduler import get_scheduler_jobs, is_scheduler_running
from app.models.etf import ETFInfo
from app.models.etl import ETLLog
from app.models.favorite import UserFavorite
from app.schemas.auth import UserResponse
from app.services.news._model_loader import NewsArticle, NewsArticleSymbol
from app.services.news.content_fetcher import ContentFetcher
from app.services.news.translation_service import NewsTranslationService

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["news"],
    dependencies=[Depends(get_current_user)],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# All concrete market buckets the news collectors have ever written
# into ``news_article.market``. ``global`` is a frontend-only sentinel
# (added in M22-2, 2026-07-04) — see ``_expand_market_filter`` below.
_GLOBAL_MARKETS: tuple[str, ...] = ("cn_a", "us", "crypto")


def _expand_market_filter(market: str | None) -> tuple[str | None, tuple[str, ...] | None]:
    """Translate the ``market`` query value into SQLAlchemy filter
    inputs.

    Returns ``(literal, tuple)``:
    - ``literal`` is set when the filter is an exact match (``"us"``).
    - ``tuple`` is set when the filter is a membership test (``"global"``).
    - Both are ``None`` when no filter is requested.

    The frontend sentinel ``"global"`` is mapped to the union of every
    concrete bucket the crawler has ever written so it surfaces every
    article regardless of market.
    """
    if not market:
        return None, None
    if market == "global":
        return None, _GLOBAL_MARKETS
    return market, None


def _apply_market_filter(stmt, count_stmt, market: str | None):
    """Apply the expanded market filter to both the data and count
    statements in one place so ``list_news`` and ``list_watchlist_news``
    stay aligned.
    """
    literal, in_list = _expand_market_filter(market)
    if literal is not None:
        stmt = stmt.where(NewsArticle.market == literal)
        count_stmt = count_stmt.where(NewsArticle.market == literal)
    elif in_list is not None:
        stmt = stmt.where(NewsArticle.market.in_(in_list))
        count_stmt = count_stmt.where(NewsArticle.market.in_(in_list))
    return stmt, count_stmt


def _iso_utc(value: datetime | None) -> str | None:
    """Serialize a datetime as an explicit UTC ISO-8601 string.

    The ``news_article.published_at`` / ``fetched_at`` columns are
    stored as naive UTC values (the SQLAlchemy column type is plain
    ``DateTime`` without tz, but every crawler normalises to UTC in
    :class:`RawArticle` before insert). When those naive values flow
    through ``datetime.isoformat()`` they come out without a timezone
    suffix, which the frontend then interprets as local time and
    displays 8 hours late for Asia/Shanghai users.

    Always emit a ``+00:00`` suffix so the API contract is unambiguous:
    every datetime field returned by this router is UTC.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    # ``timespec='seconds'`` keeps the wire format compact while still
    # giving the frontend a sub-minute resolution.
    return value.isoformat(timespec="seconds")


def _article_to_dict(
    article: NewsArticle,
    symbols: list[str] | list[dict[str, Any]] | None = None,
) -> dict:
    """Render a :class:`NewsArticle` row as a JSON-safe dict.

    ``symbols`` may be either a list of internal codes (legacy callers
    such as ``list_news`` and ``list_watchlist_news``) or a list of dicts
    with ``symbol`` / ``name`` / ``name_zh`` / ``match_type`` (used by
    ``get_article``). Either form is normalised to the dict list shape
    expected by the frontend.
    """
    normalized_symbols: list[dict[str, Any]] = []
    if symbols:
        for item in symbols:
            if isinstance(item, str):
                normalized_symbols.append({"symbol": item})
            else:
                normalized_symbols.append(item)

    return {
        "id": article.id,
        "source": article.source,
        "source_id": article.source_id,
        "url": article.url,
        "title": article.title,
        "summary": article.summary,
        "author": article.author,
        "language": article.language,
        "market": article.market,
        "category": article.category,
        "published_at": _iso_utc(article.published_at),
        "fetched_at": _iso_utc(article.fetched_at),
        "engagement": article.engagement or {},
        "sentiment_score": article.sentiment_score,
        "sentiment_label": article.sentiment_label,
        "symbols": normalized_symbols,
        # Cache slots for the Jina Reader lazy-load feature. Rows where
        # ``ai_cleanup_status == "failed"`` only contain the title +
        # date in ``full_content`` (Jina could not extract the body) —
        # hide that noise so the detail page keeps showing the summary
        # and the "load full text" button stays available for a retry.
        "full_content": (
            article.full_content if article.ai_cleanup_status != "failed" else None
        ),
        "full_content_fetched_at": (
            _iso_utc(article.full_content_fetched_at)
            if article.ai_cleanup_status != "failed"
            else None
        ),
        # Chinese translation cache (only populated for English articles;
        # the ``/translate`` endpoint enforces ``language == 'en'``).
        "translated_zh": article.translated_zh,
        "translation_generated_at": _iso_utc(article.translation_generated_at),
        # AI-cleanup observability (M22-3, 2026-07-05). ``None`` when
        # the scheduler has not yet fetched this article; one of
        # ``cleaned | skipped | failed | not_attempted`` otherwise.
        # The frontend uses ``ai_cleanup_status`` to render the
        # "AI didn't work" alert bar on the detail page.
        "ai_cleaned_at": _iso_utc(article.ai_cleaned_at),
        "ai_cleanup_status": article.ai_cleanup_status,
    }


def _parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 datetime string. Returns ``None`` for empty/invalid."""
    if not value:
        return None
    try:
        # ``datetime.fromisoformat`` handles "Z" suffix only on 3.11+.
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
def list_news(
    market: str | None = Query(
        None,
        description=(
            "Filter by market. Allowed values: cn_a | us | crypto, "
            "or the frontend sentinel ``global`` which is mapped to "
            "the union of all concrete markets."
        ),
    ),
    symbol: str | None = Query(None, description="Filter by linked instrument code"),
    source: str | None = Query(None, description="Filter by source id (e.g. xinhua_rss)"),
    from_date: str | None = Query(None, description="ISO-8601 lower bound on published_at"),
    to_date: str | None = Query(None, description="ISO-8601 upper bound on published_at"),
    q: str | None = Query(
        None,
        max_length=200,
        description=(
            "Best-effort full-text search across title, summary and "
            "content. Empty / whitespace strings are ignored."
        ),
    ),
    importance_min: int | None = Query(None, ge=1, le=5, description="Minimum importance level (1-5)"),
    event_category: list[str] | None = Query(
        None,
        description=(
            "Filter by event_category. Repeatable. Allowed: "
            "earnings|m&a|product|macro|regulation|guidance|analyst|legal|rumor"
            "|geopolitics|central_bank|election|trade_war|sanction|other"
        ),
    ),
    page: int = Query(1, ge=1, description="1-indexed page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size (1-100)"),
    db: Session = Depends(get_db),
) -> dict:
    """List news articles with optional filters and pagination."""
    from_dt = _parse_iso(from_date)
    to_dt = _parse_iso(to_date)
    if from_date and from_dt is None:
        raise HTTPException(status_code=400, detail="from_date must be ISO-8601")
    if to_date and to_dt is None:
        raise HTTPException(status_code=400, detail="to_date must be ISO-8601")

    stmt = select(NewsArticle)
    count_stmt = select(func.count(NewsArticle.id))

    stmt, count_stmt = _apply_market_filter(stmt, count_stmt, market)
    if source:
        stmt = stmt.where(NewsArticle.source == source)
        count_stmt = count_stmt.where(NewsArticle.source == source)
    if from_dt is not None:
        stmt = stmt.where(NewsArticle.published_at >= from_dt)
        count_stmt = count_stmt.where(NewsArticle.published_at >= from_dt)
    if to_dt is not None:
        stmt = stmt.where(NewsArticle.published_at <= to_dt)
        count_stmt = count_stmt.where(NewsArticle.published_at <= to_dt)
    # Best-effort full-text search across title + summary + content. We
    # use ILIKE for cross-DB portability (Postgres); spaces become AND
    # so multi-word queries narrow results. Substring search is fine for
    # the news volume (~10k rows) — no need for tsvector here.
    if q is not None and q.strip():
        from sqlalchemy import or_
        tokens = [t for t in q.strip().split() if t]
        if tokens:
            for token in tokens:
                pattern = f"%{token}%"
                stmt = stmt.where(
                    or_(
                        NewsArticle.title.ilike(pattern),
                        NewsArticle.summary.ilike(pattern),
                        NewsArticle.content.ilike(pattern),
                    )
                )
                count_stmt = count_stmt.where(
                    or_(
                        NewsArticle.title.ilike(pattern),
                        NewsArticle.summary.ilike(pattern),
                        NewsArticle.content.ilike(pattern),
                    )
                )
    if symbol:
        # Subquery for the linked-symbol filter.
        sub = (
            select(NewsArticleSymbol.article_id)
            .where(NewsArticleSymbol.symbol == symbol)
            .subquery()
        )
        stmt = stmt.where(NewsArticle.id.in_(select(sub.c.article_id)))
        count_stmt = count_stmt.where(NewsArticle.id.in_(select(sub.c.article_id)))
    if importance_min is not None:
        stmt = stmt.where(NewsArticle.importance >= importance_min)
        count_stmt = count_stmt.where(NewsArticle.importance >= importance_min)
    if event_category:
        # Allow free-form list to keep forward-compatible with new
        # categories added by the LLM prompt later (geopolitics,
        # central_bank, election, trade_war, sanction ...). Empty
        # strings are dropped so a frontend bug does not kill results.
        cats = [c for c in event_category if c]
        if cats:
            stmt = stmt.where(NewsArticle.event_category.in_(cats))
            count_stmt = count_stmt.where(NewsArticle.event_category.in_(cats))

    total = db.execute(count_stmt).scalar() or 0
    rows = db.execute(
        stmt.order_by(NewsArticle.published_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()

    items = [_article_to_dict(row) for row in rows]
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": int(total),
        "total_pages": (int(total) + page_size - 1) // page_size if total else 0,
    }


@router.get("/watchlist")
def list_watchlist_news(
    market: str | None = Query(None, description="Filter by market (cn_a | us | crypto)"),
    source: str | None = Query(None, description="Filter by source id (e.g. xinhua_rss)"),
    from_date: str | None = Query(None, description="ISO-8601 lower bound on published_at"),
    to_date: str | None = Query(None, description="ISO-8601 upper bound on published_at"),
    event_category: list[str] | None = Query(
        None,
        description=(
            "Filter by event_category. Repeatable. Allowed: "
            "earnings|m&a|product|macro|regulation|guidance|analyst|legal|rumor"
            "|geopolitics|central_bank|election|trade_war|sanction|other"
        ),
    ),
    page: int = Query(1, ge=1, description="1-indexed page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size (1-100)"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    """List news articles linked to the current user's favorites.

    Joins ``news_article_symbol`` against the user's ``user_favorite``
    rows. The response shape mirrors ``GET /news`` plus a ``watchlist``
    block that reports how many symbols were used and how many of them
    have at least one matching article — useful for surfacing
    "5 favorites, 28 articles" in the UI.
    """
    from_dt = _parse_iso(from_date)
    to_dt = _parse_iso(to_date)
    if from_date and from_dt is None:
        raise HTTPException(status_code=400, detail="from_date must be ISO-8601")
    if to_date and to_dt is None:
        raise HTTPException(status_code=400, detail="to_date must be ISO-8601")

    # Resolve the user's favorite codes up-front. An empty watchlist is
    # a legitimate state — return an empty page rather than 404 so the
    # frontend can render an empty-state.
    favorite_codes = [
        row[0]
        for row in db.execute(
            select(UserFavorite.etf_code).where(UserFavorite.username == user.username)
        ).all()
    ]
    if not favorite_codes:
        return {
            "items": [],
            "page": page,
            "page_size": page_size,
            "total": 0,
            "total_pages": 0,
            "watchlist": {
                "symbols": [],
                "symbols_with_news": 0,
                "total_articles": 0,
            },
        }

    # Subquery: article ids linked to any favorite code.
    linked_sub = (
        select(NewsArticleSymbol.article_id)
        .where(NewsArticleSymbol.symbol.in_(favorite_codes))
        .distinct()
        .subquery()
    )

    stmt = select(NewsArticle).where(NewsArticle.id.in_(select(linked_sub.c.article_id)))
    count_stmt = (
        select(func.count(NewsArticle.id))
        .where(NewsArticle.id.in_(select(linked_sub.c.article_id)))
    )

    if market:
        literal, in_list = _expand_market_filter(market)
        if literal is not None:
            stmt = stmt.where(NewsArticle.market == literal)
            count_stmt = count_stmt.where(NewsArticle.market == literal)
        elif in_list is not None:
            stmt = stmt.where(NewsArticle.market.in_(in_list))
            count_stmt = count_stmt.where(NewsArticle.market.in_(in_list))
    if source:
        stmt = stmt.where(NewsArticle.source == source)
        count_stmt = count_stmt.where(NewsArticle.source == source)
    if from_dt is not None:
        stmt = stmt.where(NewsArticle.published_at >= from_dt)
        count_stmt = count_stmt.where(NewsArticle.published_at >= from_dt)
    if to_dt is not None:
        stmt = stmt.where(NewsArticle.published_at <= to_dt)
        count_stmt = count_stmt.where(NewsArticle.published_at <= to_dt)
    if event_category:
        cats = [c for c in event_category if c]
        if cats:
            stmt = stmt.where(NewsArticle.event_category.in_(cats))
            count_stmt = count_stmt.where(NewsArticle.event_category.in_(cats))

    total = db.execute(count_stmt).scalar() or 0
    rows = db.execute(
        stmt.order_by(NewsArticle.published_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()

    # For each fetched article, hydrate its symbols so the frontend can
    # render them inline. We only need symbols for the current page,
    # not the whole result set.
    article_ids = [row.id for row in rows]
    symbols_by_article: dict[int, list[str]] = {aid: [] for aid in article_ids}
    if article_ids:
        sym_rows = db.execute(
            select(NewsArticleSymbol.article_id, NewsArticleSymbol.symbol).where(
                NewsArticleSymbol.article_id.in_(article_ids)
            )
        ).all()
        for aid, sym in sym_rows:
            symbols_by_article.setdefault(aid, []).append(sym)

    items = [_article_to_dict(row, symbols=symbols_by_article.get(row.id, [])) for row in rows]

    # Per-favorite coverage count — how many of the user's symbols
    # actually have at least one matching article within the current
    # filters. Used by the UI for the "自选标的 X 个 · 相关资讯 Y 条"
    # summary. We respect the same market/source/date filters so the
    # number tracks what the user is actually seeing on the page.
    covered_q = (
        select(NewsArticleSymbol.symbol)
        .join(NewsArticle, NewsArticle.id == NewsArticleSymbol.article_id)
        .where(NewsArticleSymbol.symbol.in_(favorite_codes))
    )
    if market:
        literal, in_list = _expand_market_filter(market)
        if literal is not None:
            covered_q = covered_q.where(NewsArticle.market == literal)
        elif in_list is not None:
            covered_q = covered_q.where(NewsArticle.market.in_(in_list))
    if source:
        covered_q = covered_q.where(NewsArticle.source == source)
    if from_dt is not None:
        covered_q = covered_q.where(NewsArticle.published_at >= from_dt)
    if to_dt is not None:
        covered_q = covered_q.where(NewsArticle.published_at <= to_dt)
    if event_category:
        cats = [c for c in event_category if c]
        if cats:
            covered_q = covered_q.where(NewsArticle.event_category.in_(cats))
    covered_set = {sym for (sym,) in db.execute(covered_q.distinct()).all()}

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": int(total),
        "total_pages": (int(total) + page_size - 1) // page_size if total else 0,
        "watchlist": {
            "symbols": favorite_codes,
            "symbols_with_news": len(covered_set),
            "total_articles": int(total),
        },
    }


@router.get("/stats/sources")
def source_stats(db: Session = Depends(get_db)) -> dict:
    """Per-source ingestion counts for the last 7 days.

    Returns a dict ``{source: {total, last_7d, last_24h}}`` sorted by
    total descending. The numbers come straight from
    ``news_article.fetched_at`` so they reflect rows that were
    actually persisted.
    """
    now = datetime.now(tz=timezone.utc)
    cutoff_7d = now - timedelta(days=7)
    cutoff_24h = now - timedelta(hours=24)

    rows = db.execute(
        select(
            NewsArticle.source,
            func.count(NewsArticle.id).label("total"),
            func.sum(
                case((NewsArticle.fetched_at >= cutoff_7d, 1), else_=0)
            ).label("last_7d"),
            func.sum(
                case((NewsArticle.fetched_at >= cutoff_24h, 1), else_=0)
            ).label("last_24h"),
        )
        .group_by(NewsArticle.source)
        .order_by(func.count(NewsArticle.id).desc())
    ).all()

    sources: list[dict[str, Any]] = []
    for source, total, last_7d, last_24h in rows:
        sources.append(
            {
                "source": source,
                "total": int(total or 0),
                "last_7d": int(last_7d or 0),
                "last_24h": int(last_24h or 0),
            }
        )
    return {
        "as_of": now.isoformat(),
        "sources": sources,
    }


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

class NewsWorkerStatus(BaseModel):
    """资讯 / 情绪 worker 的运行状态（由 ``/news/health`` 返回）.

    ``name`` 是 APScheduler 里的 ``job.id``；``label`` 和 ``schedule`` 是
    给前端展示用的中文映射。对没有直接 ``news_article.source`` 的情绪
    任务（如批量处理、低延迟、事件分类），``articles_24h`` 固定为 0。
    """

    name: str
    label: str
    schedule: str
    last_run: str | None
    last_status: str
    last_records: int | None
    last_error: str | None
    articles_24h: int


# Worker job ids that the NewsHealth panel should render.  We match by
# keyword so new sources added to the scheduler are surfaced automatically,
# and we hard-code the display label + cadence for known jobs.
_WORKER_KEYWORDS: tuple[str, ...] = (
    "reddit",
    "coindesk",
    "cointelegraph",
    "xueqiu",
    "sentiment",
    "categorization",
    "retail",
    "full_content",
)

_WORKER_META: dict[str, dict[str, str]] = {
    "news_reddit_5m": {"label": "Reddit 散户讨论", "schedule": "每 5 分钟"},
    "news_coindesk_5m": {"label": "CoinDesk RSS", "schedule": "每 5 分钟"},
    "news_cointelegraph_5m": {"label": "Cointelegraph RSS", "schedule": "每 5 分钟"},
    "news_xueqiu_5m": {"label": "雪球 散户讨论", "schedule": "每 5 分钟"},
    "news_full_content_10m": {"label": "资讯全文抓取", "schedule": "每 10 分钟"},
    "sentiment_batch_30s": {"label": "情绪批量处理", "schedule": "每 30 秒"},
    "sentiment_low_latency_5m": {"label": "情绪低延迟处理", "schedule": "每 5 分钟"},
    "news_article_categorization_1m": {"label": "新闻事件分类", "schedule": "每 1 分钟"},
    "sentiment_retail_agg_30m": {"label": "散户讨论聚合", "schedule": "每 30 分钟"},
}

# Map a worker job id to the ``news_article.source`` it writes.  Only
# source-type crawlers have this mapping; sentiment-only jobs have none.
_WORKER_JOB_TO_SOURCE: dict[str, str] = {
    "news_reddit_5m": "reddit",
    "news_coindesk_5m": "coindesk",
    "news_cointelegraph_5m": "cointelegraph",
    "news_xueqiu_5m": "xueqiu",
}


def _worker_articles_24h(db: Session, job_id: str) -> int:
    """Count articles written by ``job_id``'s source in the last 24h."""
    source = _WORKER_JOB_TO_SOURCE.get(job_id)
    if not source:
        return 0
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    return (
        db.execute(
            select(func.count(NewsArticle.id)).where(
                NewsArticle.source == source,
                NewsArticle.fetched_at >= cutoff,
            )
        ).scalar()
        or 0
    )


def _worker_status_row(db: Session, job_id: str, job_name: str) -> dict[str, Any]:
    """Build a ``NewsWorkerStatus`` dict for a single scheduler job."""
    meta = _WORKER_META.get(
        job_id, {"label": job_name or job_id, "schedule": "unknown"}
    )
    last_run = (
        db.query(ETLLog)
        .filter(ETLLog.job_name == job_id)
        .order_by(desc(ETLLog.created_at))
        .first()
    )
    if last_run is None:
        return {
            "name": job_id,
            "label": meta["label"],
            "schedule": meta["schedule"],
            "last_run": None,
            "last_status": "never_run",
            "last_records": None,
            "last_error": None,
            "articles_24h": _worker_articles_24h(db, job_id),
        }

    status = last_run.status
    if status not in ("success", "failed"):
        status = "unknown"

    error = last_run.error_msg
    if error:
        error = error[:200]

    return {
        "name": job_id,
        "label": meta["label"],
        "schedule": meta["schedule"],
        "last_run": _iso_utc(last_run.end_time),
        "last_status": status,
        "last_records": last_run.records_count,
        "last_error": error,
        "articles_24h": _worker_articles_24h(db, job_id),
    }


# News source identifiers used in ``NewsArticle.source``. Kept in sync
# with ``app/services/news/sources/*.py`` ``source_name`` declarations.
# NOTE: xinhua_rss is temporarily omitted because its public RSS endpoints
# return 404.
_NEWS_SOURCES: list[str] = [
    "cninfo",
    "sina_finance",
    "wechat_zeping",
    "yahoo_finance",
    "cnbc",
    "sec_edgar",
    "reddit",
    "xueqiu",
    "coindesk",
    "cointelegraph",
]

# Map each NewsArticle source to the scheduler job_id (defined in
# ``app/core/scheduler.py``). Used to look up the latest ETL log row
# for that job.
_SOURCE_TO_JOB: dict[str, str] = {
    "cninfo": "news_cninfo_10m",
    "sina_finance": "news_sina_5m",
    "wechat_zeping": "news_wechat_zeping_15m",
    "yahoo_finance": "news_yahoo_5m",
    "cnbc": "news_cnbc_5m",
    "sec_edgar": "news_sec_edgar_30m",
    "reddit": "news_reddit_5m",
    "xueqiu": "news_xueqiu_5m",
    "coindesk": "news_coindesk_5m",
    "cointelegraph": "news_cointelegraph_5m",
}


def _source_health_row(db: Session, source: str) -> dict[str, Any]:
    """Build the diagnostics row for a single NewsArticle source."""
    now = datetime.now(tz=timezone.utc)
    cutoff_24h = now - timedelta(hours=24)

    # Aggregate total + last 24h + latest published_at + latest fetched_at
    # in a single query so we don't N+1 the DB.
    agg_row = db.execute(
        select(
            func.count(NewsArticle.id).label("total"),
            func.sum(case((NewsArticle.fetched_at >= cutoff_24h, 1), else_=0)).label(
                "last_24h"
            ),
            func.max(NewsArticle.published_at).label("last_published_at"),
            func.max(NewsArticle.fetched_at).label("last_fetched_at"),
        ).where(NewsArticle.source == source)
    ).one()

    total = int(agg_row.total or 0)
    last_24h = int(agg_row.last_24h or 0)
    last_published_at = agg_row.last_published_at
    last_fetched_at = agg_row.last_fetched_at

    # Latest etl_log row for the matching scheduler job (if any).
    job_id = _SOURCE_TO_JOB.get(source)
    etl: dict[str, Any] | None = None
    if job_id:
        last_run = (
            db.query(ETLLog)
            .filter(ETLLog.job_name == job_id)
            .order_by(desc(ETLLog.created_at))
            .first()
        )
        if last_run is not None:
            etl = {
                "status": last_run.status,
                "records": last_run.records_count,
                "error_msg": last_run.error_msg,
                "finished_at": _iso_utc(last_run.end_time),
                "started_at": _iso_utc(last_run.start_time),
            }

    return {
        "source": source,
        "job_id": job_id,
        "total": total,
        "last_24h": last_24h,
        "last_published_at": _iso_utc(last_published_at),
        "last_fetched_at": _iso_utc(last_fetched_at),
        "latest_etl": etl,
    }


@router.get("/health")
def news_health(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Per-source diagnostic: latest article time + 24h count + scheduler status.

    Used by the ``NewsHealth`` operations dashboard. Returns gracefully
    even when the scheduler is dead (the dashboard then renders
    ``scheduler_running=false`` and the source rows stay red).

    M22-3 (2026-07-05) also returns ``ai_cleanup_24h`` — the AI
    cleanup breakdown for the last 24 hours. The frontend uses
    ``cleaned_pct`` to decide whether to render the "AI 清理失败率
    过高" warning card. Threshold is configurable via
    ``news_ai_cleanup_alert_pct`` (default ``70.0``).

    M22-4 (2026-07-18) also returns ``workers`` — the health panel for
    the 8 news / sentiment workers so the frontend can render the
    scheduler job grid without a second endpoint.
    """
    now = datetime.now(tz=timezone.utc)

    sources = [_source_health_row(db, src) for src in _NEWS_SOURCES]

    # Scheduler introspection — safe even when the BackgroundScheduler
    # was never started (returns empty list + running=false).
    scheduler_running = is_scheduler_running()
    scheduler_jobs = get_scheduler_jobs()
    news_jobs = [
        j for j in scheduler_jobs if j["id"].startswith("news_")
    ]

    # Worker health rows: any job whose id contains a news/sentiment
    # keyword.  This is intentionally broader than the fixed 8 ids so
    # new crawlers appear automatically.
    worker_jobs = [
        j for j in scheduler_jobs
        if any(k in j["id"] for k in _WORKER_KEYWORDS)
    ]
    workers = [
        _worker_status_row(db, j["id"], j.get("name", j["id"]))
        for j in worker_jobs
    ]

    # AI-cleanup observability (M22-3). Counts only the rows the
    # scheduler actually reached in the last 24 h
    # (``ai_cleaned_at >= now - 24h``) so a backlog of stale rows
    # does not inflate "cleaned" denominators.
    cutoff_24h = now - timedelta(hours=24)
    ai_counts = db.execute(
        select(
            func.count(NewsArticle.id).label("total"),
            func.sum(
                case((NewsArticle.ai_cleanup_status == "cleaned", 1), else_=0)
            ).label("cleaned"),
            func.sum(
                case((NewsArticle.ai_cleanup_status == "skipped", 1), else_=0)
            ).label("skipped"),
            func.sum(
                case((NewsArticle.ai_cleanup_status == "failed", 1), else_=0)
            ).label("failed"),
        ).where(NewsArticle.ai_cleaned_at >= cutoff_24h)
    ).one()
    ai_total = int(ai_counts.total or 0)
    ai_cleaned = int(ai_counts.cleaned or 0)
    ai_skipped = int(ai_counts.skipped or 0)
    ai_failed = int(ai_counts.failed or 0)
    # ``cleaned_pct`` is the share of *processed* rows (excludes
    # skipped — if DeepSeek was never configured, the alert would
    # fire even though nothing is actually broken).
    processed = ai_cleaned + ai_failed
    ai_cleaned_pct = round(ai_cleaned / processed * 100, 1) if processed else 0.0

    alert_threshold_pct = float(
        get_settings().news_ai_cleanup_alert_pct
    )
    ai_alert = (
        processed > 0 and ai_cleaned_pct < alert_threshold_pct
    )

    return {
        "as_of": now.isoformat(),
        "scheduler_running": scheduler_running,
        "scheduler_jobs": news_jobs,
        "scheduler_total_jobs": len(scheduler_jobs),
        "sources": sources,
        "workers": workers,
        "ai_cleanup_24h": {
            "total": ai_total,
            "cleaned": ai_cleaned,
            "skipped": ai_skipped,
            "failed": ai_failed,
            "cleaned_pct": ai_cleaned_pct,
            "alert_threshold_pct": alert_threshold_pct,
            "alert": ai_alert,
        },
    }
@router.get("/retail-sentiment/{symbol}")
def get_retail_sentiment(
    symbol: str,
    window: str = Query("7d", description="Look-back window, e.g. 7d, 30d"),
    db: Session = Depends(get_db),
) -> dict:
    """Aggregated retail-discussion sentiment for a single symbol.

    Computes an importance-weighted sentiment summary from news / social
    articles linked to ``symbol`` in the requested window. Falls back to
    all linked articles when no retail-specific sources (reddit / xueqiu)
    are available. The returned shape matches the frontend
    ``RetailSentiment`` contract.
    """
    try:
        days = int("".join(c for c in window if c.isdigit()) or "7")
    except ValueError:
        days = 7
    days = max(1, min(days, 90))
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)

    # Retail sources first; if nothing matches, fall back to any linked article.
    retail_sources = {"reddit", "xueqiu"}

    def _query(sources: set[str] | None) -> Any:
        q = (
            select(NewsArticle)
            .join(NewsArticleSymbol, NewsArticle.id == NewsArticleSymbol.article_id)
            .where(NewsArticleSymbol.symbol == symbol)
            .where(NewsArticle.published_at >= since)
        )
        if sources:
            q = q.where(NewsArticle.source.in_(sources))
        return q

    rows = db.execute(_query(retail_sources).order_by(NewsArticle.published_at.desc())).scalars().all()
    if not rows:
        rows = db.execute(_query(None).order_by(NewsArticle.published_at.desc())).scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No sentiment data for {symbol}")

    scores: list[float] = []
    weights: list[float] = []
    bull = bear = neutral = 0
    themes: dict[str, float] = {}
    total_weight = 0.0

    for article in rows:
        weight = float(article.importance or 3)
        score_raw = article.sentiment_score
        if score_raw is not None:
            score = float(score_raw)
            # Normalise to [-1, 1] if stored as -100..100.
            if abs(score) > 1:
                score = score / 100.0
            scores.append(score)
            weights.append(weight)
            total_weight += weight

        label = article.sentiment_label
        if label == "positive" or label == "bullish":
            bull += weight
        elif label == "negative" or label == "bearish":
            bear += weight
        else:
            neutral += weight

        # Aggregate driver keywords as themes.
        drivers = article.sentiment_drivers
        if drivers:
            if isinstance(drivers, list):
                for d in drivers:
                    themes[str(d)] = themes.get(str(d), 0.0) + weight
        elif article.event_category:
            themes[article.event_category] = themes.get(article.event_category, 0.0) + weight

    if total_weight > 0 and scores:
        overall = sum(s * w for s, w in zip(scores, weights)) / total_weight
    else:
        overall = 0.0

    sentiment_total = bull + bear + neutral or 1.0
    bull_ratio = bull / sentiment_total
    bear_ratio = bear / sentiment_total

    # Controversy: high when bull and bear are close in size.
    if bull + bear > 0:
        controversy = 1.0 - abs(bull - bear) / (bull + bear)
    else:
        controversy = 0.0
    controversy = max(0.0, min(1.0, controversy))

    # Top themes by weighted share.
    main_themes = []
    if themes:
        theme_total = sum(themes.values()) or 1.0
        sorted_themes = sorted(themes.items(), key=lambda x: x[1], reverse=True)
        main_themes = [
            {"theme": t, "percentage": round(w / theme_total * 100, 1)}
            for t, w in sorted_themes[:5]
        ]

    # Simple summary string; no LLM required for v1.
    label_text = "看多" if overall > 0.15 else "看空" if overall < -0.15 else "中性"
    summary = (
        f"最近 {days} 天 {symbol} 散户情绪{label_text}。"
        f"共 {len(rows)} 条讨论，多空比 {bull_ratio:.0%}:{bear_ratio:.0%}。"
    )
    if main_themes:
        summary += f"主要话题: {', '.join(t['theme'] for t in main_themes[:3])}。"

    return {
        "symbol": symbol,
        "overall": round(overall, 4),
        "bull_bear_ratio": {
            "bull": round(bull_ratio, 4),
            "bear": round(bear_ratio, 4),
        },
        "main_themes": main_themes,
        "controversy": round(controversy, 4),
        "summary": summary,
        "window": f"{days}d",
        "article_count": len(rows),
    }


@router.get("/{article_id}")
def get_article(article_id: int, db: Session = Depends(get_db)) -> dict:
    """Return a single article plus its linked symbols.

    Each symbol is returned as a dict with ``symbol``, ``match_type``,
    ``name`` and ``name_zh``. The name fields are read from the
    ``news_article_symbol`` cache when present; otherwise we fall back to
    a bulk lookup against ``etf_info`` so older rows still render useful
    labels.
    """
    article = db.get(NewsArticle, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail=f"article {article_id} not found")

    symbol_rows = db.execute(
        select(
            NewsArticleSymbol.symbol,
            NewsArticleSymbol.match_type,
            NewsArticleSymbol.name,
            NewsArticleSymbol.name_zh,
        ).where(NewsArticleSymbol.article_id == article_id)
    ).all()

    # Backfill any missing names from etf_info in one query.
    codes_missing_name = [
        row.symbol
        for row in symbol_rows
        if row.name is None or row.name_zh is None
    ]
    etf_by_code: dict[str, Any] = {}
    if codes_missing_name:
        etf_rows = db.execute(
            select(ETFInfo.code, ETFInfo.name, ETFInfo.name_zh).where(
                ETFInfo.code.in_(codes_missing_name)
            )
        ).all()
        etf_by_code = {row.code: row for row in etf_rows}

    symbols: list[dict[str, Any]] = []
    for row in symbol_rows:
        name = row.name
        name_zh = row.name_zh
        if name is None or name_zh is None:
            etf = etf_by_code.get(row.symbol)
            if etf:
                name = name or etf.name
                name_zh = name_zh or etf.name_zh
        symbols.append(
            {
                "symbol": row.symbol,
                "match_type": row.match_type,
                "name": name,
                "name_zh": name_zh,
            }
        )

    return _article_to_dict(article, symbols=symbols)


@router.post("/{article_id}/fetch-content")
def fetch_article_content(
    article_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Fetch the full article body via Jina Reader and cache it.

    Returns ``{success, content, cached, error}``. On failure the
    caller (the frontend detail page) should fall back to ``body`` /
    ``summary`` already present on the article.

    Requires auth (``get_current_user`` is wired by the router-level
    ``dependencies``). Triggers a real network call — see
    :class:`app.services.news.content_fetcher.ContentFetcher`.
    """
    article = db.get(NewsArticle, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail=f"article {article_id} not found")

    fetcher = ContentFetcher(db)
    result = fetcher.fetch(article_id)

    if not result.success:
        # 502 lets the frontend distinguish "Jina failed" from a 404.
        # We still echo the article's intro/summary so the user has
        # something to read instead of a broken page.
        return {
            "success": False,
            "cached": False,
            "content": article.summary or article.body,
            "error": result.error or "unknown error",
        }

    return {
        "success": True,
        "cached": result.cached,
        "content": result.content,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Translation (en → zh, DeepSeek)
# ---------------------------------------------------------------------------


@router.post("/{article_id}/translate")
def translate_article(
    article_id: int,
    target_language: str = Query(
        "zh", description="Target language code (only 'zh' is supported in v1)"
    ),
    db: Session = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> dict:
    """Translate an English news article to Chinese via DeepSeek.

    Mirrors the ``/research-reports/{id}/summarize`` flow:

    * Per-user daily counter in Redis (24h TTL, fail-open if Redis is
      down) capped at ``news_translate_daily_limit``.
    * 60s Redis lock to serialize concurrent translate calls so two
      users clicking the button at the same time don't both hit the LLM.
    * The translation is persisted on ``news_article.translated_zh`` so
      a second call is a cache hit (no LLM cost, no rate-limit burn).

    Returns ``{translation, cached, tokens_used, generated_at,
    source_language, target_language}``. Errors:

    * 404 — article not found
    * 400 — non-English article, empty body, or unsupported target
    * 429 — daily limit exceeded
    * 409 — concurrent translate already in progress
    * 502 — LLM provider call failed (no key, timeout, 5xx…)
    """
    # Per-user daily counter. Keyed by user + ISO date so it rolls
    # over at midnight UTC. Redis-down → fail-open (logged + skip).
    daily_limit = get_settings().news_translate_daily_limit
    today = date.today().isoformat()
    counter_key = f"news_translate_user:{current_user.id}:{today}"
    try:
        redis_client = get_redis_client()
        current = redis_client.incr(counter_key)
        if current == 1:
            redis_client.expire(counter_key, 86400)
        if current > daily_limit:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"今日翻译次数已达上限（{daily_limit} 次），"
                    "明天 0 点重置"
                ),
            )
    except redis.RedisError as exc:
        logger.warning("news_translate rate-limit unavailable (Redis error): %s", exc)
    except HTTPException:
        raise

    with redis_lock(f"news_translate:{article_id}", expire_seconds=60) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=409,
                detail="该文章正在翻译中，请稍后再试",
            )
        service = NewsTranslationService(db)
        try:
            result = service.translate(article_id, target_language=target_language)
        except ValueError as exc:
            msg = str(exc)
            if "not found" in msg:
                raise HTTPException(status_code=404, detail=msg)
            # Language / empty-body / unsupported target — all client errors.
            raise HTTPException(status_code=400, detail=msg)
        except RuntimeError as exc:
            # Provider unavailable / LLM call failed.
            raise HTTPException(status_code=502, detail=str(exc))
        return result


@router.get("/event-signals")
def event_signals(
    days: int = Query(7, ge=1, le=30),
    market: str | None = Query(None, description="Filter by market (cn_a | us | crypto | global)"),
    category: list[str] | None = Query(
        None,
        description=(
            "Filter by event_category. Repeatable. Allowed: "
            "earnings|m&a|product|macro|regulation|guidance|analyst|legal|rumor"
            "|geopolitics|central_bank|election|trade_war|sanction|other"
        ),
    ),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Event-driven signals from ``news_article``.

    Returns articles whose ``event_category`` is set and ``importance >= 3``
    as actionable signals.  ``signal_direction`` is derived from
    ``sentiment_label`` and ``signal_strength`` from ``importance`` (1-5
    mapped to 1-100).  Used by the SignalDashboard "事件信号" integration.
    """
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)

    stmt = select(NewsArticle).where(
        NewsArticle.event_category.isnot(None),
        NewsArticle.importance >= 3,
        NewsArticle.published_at >= since,
    )
    count_stmt = select(func.count(NewsArticle.id)).where(
        NewsArticle.event_category.isnot(None),
        NewsArticle.importance >= 3,
        NewsArticle.published_at >= since,
    )
    stmt, count_stmt = _apply_market_filter(stmt, count_stmt, market)
    if category:
        cats = [c for c in category if c]
        if cats:
            stmt = stmt.where(NewsArticle.event_category.in_(cats))
            count_stmt = count_stmt.where(NewsArticle.event_category.in_(cats))

    rows = db.execute(
        stmt.order_by(NewsArticle.published_at.desc()).limit(limit)
    ).scalars().all()

    # Hydrate linked symbols.
    article_ids = [row.id for row in rows]
    symbols_by_article: dict[int, list[dict[str, Any]]] = {}
    if article_ids:
        symbol_rows = db.execute(
            select(
                NewsArticleSymbol.article_id,
                NewsArticleSymbol.symbol,
                NewsArticleSymbol.name,
                NewsArticleSymbol.name_zh,
            ).where(NewsArticleSymbol.article_id.in_(article_ids))
        ).all()
        for article_id, symbol, name, name_zh in symbol_rows:
            symbols_by_article.setdefault(article_id, []).append(
                {"symbol": symbol, "name": name, "name_zh": name_zh}
            )

    items: list[dict[str, Any]] = []
    for article in rows:
        if article.sentiment_label == "positive" or article.sentiment_label == "bullish":
            direction = "bullish"
        elif article.sentiment_label == "negative" or article.sentiment_label == "bearish":
            direction = "bearish"
        else:
            direction = "neutral"

        strength = (article.importance or 3) * 20

        items.append(
            {
                "id": article.id,
                "title": article.title,
                "source": article.source,
                "url": article.url,
                "market": article.market,
                "event_category": article.event_category,
                "importance": article.importance,
                "sentiment_score": article.sentiment_score,
                "sentiment_label": article.sentiment_label,
                "published_at": _iso_utc(article.published_at),
                "summary": article.summary,
                "symbols": symbols_by_article.get(article.id, []),
                "signal_direction": direction,
                "signal_strength": strength,
            }
        )

    return {"items": items}


