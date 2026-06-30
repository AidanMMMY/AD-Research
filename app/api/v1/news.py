"""News API routes.

Exposes the ``news_article`` and ``news_article_symbol`` tables for
frontend consumers:

* ``GET  /news``               — list + filter + paginate
* ``GET  /news/{article_id}``  — detail + linked symbols
* ``GET  /news/stats/sources`` — per-source ingestion volume (last 7d)

All routes require a valid JWT. Crawler / scheduler backends hit the
DB directly via :mod:`app.services.news.normalizer` — these endpoints
are read-only.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.services.news._model_loader import NewsArticle, NewsArticleSymbol

router = APIRouter(
    tags=["news"],
    dependencies=[Depends(get_current_user)],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _article_to_dict(article: NewsArticle, symbols: list[str] | None = None) -> dict:
    """Render a :class:`NewsArticle` row as a JSON-safe dict."""
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
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "fetched_at": article.fetched_at.isoformat() if article.fetched_at else None,
        "engagement": article.engagement or {},
        "sentiment_score": article.sentiment_score,
        "sentiment_label": article.sentiment_label,
        "symbols": symbols or [],
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
    market: str | None = Query(None, description="Filter by market (cn_a | us | crypto)"),
    symbol: str | None = Query(None, description="Filter by linked instrument code"),
    source: str | None = Query(None, description="Filter by source id (e.g. xinhua_rss)"),
    from_date: str | None = Query(None, description="ISO-8601 lower bound on published_at"),
    to_date: str | None = Query(None, description="ISO-8601 upper bound on published_at"),
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

    if market:
        stmt = stmt.where(NewsArticle.market == market)
        count_stmt = count_stmt.where(NewsArticle.market == market)
    if source:
        stmt = stmt.where(NewsArticle.source == source)
        count_stmt = count_stmt.where(NewsArticle.source == source)
    if from_dt is not None:
        stmt = stmt.where(NewsArticle.published_at >= from_dt)
        count_stmt = count_stmt.where(NewsArticle.published_at >= from_dt)
    if to_dt is not None:
        stmt = stmt.where(NewsArticle.published_at <= to_dt)
        count_stmt = count_stmt.where(NewsArticle.published_at <= to_dt)
    if symbol:
        # Subquery for the linked-symbol filter.
        sub = (
            select(NewsArticleSymbol.article_id)
            .where(NewsArticleSymbol.symbol == symbol)
            .subquery()
        )
        stmt = stmt.where(NewsArticle.id.in_(select(sub.c.article_id)))
        count_stmt = count_stmt.where(NewsArticle.id.in_(select(sub.c.article_id)))

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


@router.get("/{article_id}")
def get_article(article_id: int, db: Session = Depends(get_db)) -> dict:
    """Return a single article plus its linked symbols."""
    article = db.get(NewsArticle, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail=f"article {article_id} not found")
    symbol_rows = db.execute(
        select(NewsArticleSymbol.symbol).where(NewsArticleSymbol.article_id == article_id)
    ).all()
    symbols = [s[0] for s in symbol_rows]
    return _article_to_dict(article, symbols=symbols)
