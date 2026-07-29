"""AI summary drain pipeline for news articles (方向 D, 2026-07-29).

Entry point:

* :func:`run_summarize_pending` — 10-minute APScheduler drain job
  (``news_summarize_10m``) that picks articles with
  ``summary_zh IS NULL AND importance >= 3`` and generates a
  one-sentence Chinese summary via :class:`NewsSummaryService`,
  highest-importance / newest first.

Fully fail-safe, mirroring ``scheduler_translate_news``: an LLM outage
records a skipped run instead of crashing the scheduler, and a failure
on one row leaves it untouched so the next tick retries.

Only ``importance >= 3`` rows are summarized — the summary is a
feed-scanning aid for notable news, and gating keeps the LLM spend
proportional to what users actually read (see the cost note on
``news_summary_batch_size`` in ``app/config.py``).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import select

logger = logging.getLogger(__name__)


def _pending_summary_ids(db, limit: int) -> list[int]:
    """Ids of unsummarized articles at/above the importance gate.

    Importance-desc then newest-first so the headlines that matter get
    a digest line first; the drain job then walks backwards into the
    archive one batch per tick.
    """
    from app.services.news._model_loader import NewsArticle

    stmt = (
        select(NewsArticle.id)
        .where(
            NewsArticle.summary_zh.is_(None),
            NewsArticle.importance.isnot(None),
            NewsArticle.importance >= 3,
        )
        .order_by(NewsArticle.importance.desc(), NewsArticle.published_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


def run_summarize_pending(batch_size: int | None = None) -> dict[str, Any]:
    """APScheduler drain job: summarize a batch of pending articles.

    Returns an ETLLog-friendly dict (``written`` = rows that got a new
    summary). When the LLM provider is not configured the whole batch is
    reported as ``skipped`` without touching any row — the same
    fail-safe contract as the translation drain.
    """
    from app.config import get_settings
    from app.core.database import SessionLocal
    from app.services.llm import get_llm_provider
    from app.services.news.summary_service import NewsSummaryService

    settings = get_settings()
    limit = batch_size or settings.news_summary_batch_size

    # Up-front provider gate: no point selecting rows we cannot process.
    provider = get_llm_provider()
    if not provider.is_available:
        logger.info("news summarize drain skipped: LLM provider unavailable")
        return {"fetched": 0, "written": 0, "skipped": 0, "reason": "provider_unavailable"}

    db = SessionLocal()
    try:
        ids = _pending_summary_ids(db, limit)
    finally:
        db.close()

    if not ids:
        return {"fetched": 0, "written": 0, "skipped": 0}

    stats = {"attempted": 0, "written": 0, "skipped": 0}
    started = time.monotonic()
    # Generous budget: the drain tick is allowed to finish its batch.
    # ``max_instances=1`` on the APScheduler registration prevents
    # overlap when a tick runs long.
    budget = 600

    db = SessionLocal()
    try:
        service = NewsSummaryService(db)
        for article_id in ids:
            if time.monotonic() - started > budget:
                break
            stats["attempted"] += 1
            try:
                result = service.summarize(article_id)
                if result.get("skipped"):
                    stats["skipped"] += 1
                else:
                    stats["written"] += 1
            except Exception as exc:  # pragma: no cover - defensive
                logger.info("auto-summarize failed for %s: %s", article_id, exc)
                db.rollback()
                stats["skipped"] += 1
    finally:
        db.close()

    if stats["written"] or stats["skipped"]:
        logger.info("news summarize drain: %s", stats)
    return {
        "fetched": len(ids),
        "written": stats["written"],
        "skipped": stats["skipped"],
    }
