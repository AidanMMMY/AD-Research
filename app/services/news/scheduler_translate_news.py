"""Auto-translation pipeline for non-Chinese news articles.

Two entry points, mirroring ``scheduler_fetch_full_content``:

* :func:`auto_translate_for_ids` — called inline from the crawler write
  path (``scheduler_jobs._write_to_db``) right after the full-content
  fetch, bounded by ``news_translation_ingest_time_budget_sec`` so a
  slow LLM can never stall the crawl tick.
* :func:`run_translate_pending` — 10-minute APScheduler drain job that
  picks up whatever the ingest pass missed (budget exhausted, LLM
  hiccup) and gradually backfills older untranslated rows, newest
  first.

Both are fully fail-safe: a translation failure leaves the row
untouched (``title_zh`` / ``translated_zh`` stay ``NULL``) so the next
tick retries, and Chinese articles are skipped by the service layer.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import select

logger = logging.getLogger(__name__)


def auto_translate_for_ids(
    article_ids: list[int], *, time_budget_sec: int | None = None
) -> dict[str, int]:
    """Translate a batch of freshly-ingested articles, best-effort.

    Each article gets a title translation (when missing) and a body
    translation (when missing) via
    :meth:`NewsTranslationService.auto_translate`. The loop stops when
    the time budget is exhausted — remaining rows are left for the
    drain job.
    """
    if not article_ids:
        return {"attempted": 0, "translated": 0, "skipped": 0, "budget_exhausted": 0}

    from app.config import get_settings
    from app.core.database import SessionLocal
    from app.services.news.translation_service import NewsTranslationService

    settings = get_settings()
    if not settings.news_translation_on_ingest:
        return {"attempted": 0, "translated": 0, "skipped": 0, "budget_exhausted": 0}
    budget = time_budget_sec or settings.news_translation_ingest_time_budget_sec

    stats = {"attempted": 0, "translated": 0, "skipped": 0, "budget_exhausted": 0}
    started = time.monotonic()
    db = SessionLocal()
    try:
        service = NewsTranslationService(db)
        for article_id in article_ids:
            if time.monotonic() - started > budget:
                stats["budget_exhausted"] = len(article_ids) - stats["attempted"]
                break
            stats["attempted"] += 1
            try:
                result = service.auto_translate(article_id)
                if result.get("skipped"):
                    stats["skipped"] += 1
                elif result.get("translated") or result.get("title_zh"):
                    stats["translated"] += 1
            except Exception as exc:  # pragma: no cover - defensive
                logger.info("auto-translate failed for %s: %s", article_id, exc)
                db.rollback()
    finally:
        db.close()

    if stats["translated"] or stats["budget_exhausted"]:
        logger.info("news auto-translate (ingest): %s", stats)
    return stats


def _pending_translation_ids(db, limit: int) -> list[int]:
    """Ids of non-Chinese articles still missing a translation.

    Newest first so recent headlines get Chinese titles quickly; the
    drain job then walks backwards into the archive one batch per tick.
    """
    from app.services.news._model_loader import NewsArticle
    from app.services.news.translation_service import _CHINESE_LANGUAGE_CODES

    stmt = (
        select(NewsArticle.id)
        .where(
            # ``language`` is NOT NULL with default 'en' for the English
            # sources; the ``~in_`` guard keeps every Chinese variant out.
            NewsArticle.language.isnot(None),
            NewsArticle.language.notin_(sorted(_CHINESE_LANGUAGE_CODES)),
            (NewsArticle.title_zh.is_(None))
            | (NewsArticle.translated_zh.is_(None))
            # Stale re-translation (2026-07-27): the cached translation
            # was made from the RSS excerpt and the full body arrived
            # afterwards — redo it so the reader gets the FULL Chinese
            # text, not a translated teaser.
            | (
                NewsArticle.translated_zh.isnot(None)
                & NewsArticle.full_content_fetched_at.isnot(None)
                & NewsArticle.translation_generated_at.isnot(None)
                & (
                    NewsArticle.full_content_fetched_at
                    > NewsArticle.translation_generated_at
                )
            ),
        )
        .order_by(NewsArticle.published_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


def run_translate_pending(batch_size: int | None = None) -> dict[str, Any]:
    """APScheduler drain job: translate a batch of pending articles.

    Returns an ETLLog-friendly dict (``written`` = rows that got at
    least one new translation).
    """
    from app.config import get_settings
    from app.core.database import SessionLocal
    from app.services.news.translation_service import NewsTranslationService

    settings = get_settings()
    limit = batch_size or settings.news_translation_batch_size

    db = SessionLocal()
    try:
        ids = _pending_translation_ids(db, limit)
    finally:
        db.close()

    if not ids:
        return {"fetched": 0, "written": 0}

    # Generous budget: the drain tick is allowed to finish its batch.
    # ``max_instances=1`` on the APScheduler registration prevents
    # overlap when a tick runs long.
    stats = auto_translate_for_ids(ids, time_budget_sec=600)
    return {
        "fetched": len(ids),
        "written": stats["translated"],
        "skipped": stats["skipped"],
    }
