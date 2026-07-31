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

Both are fully fail-safe: a translation failure increments the row's
``translation_attempts`` counter (rows leave the retry set at
``_MAX_TRANSLATION_ATTEMPTS``, or immediately for deterministic
sensitive-content rejections) and Chinese articles are skipped by the
service layer.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy import and_, or_, select

logger = logging.getLogger(__name__)


def _translate_one(article_id: int) -> dict[str, Any]:
    """Translate a single article in its own DB session.

    Worker for the concurrent batch loop below — SQLAlchemy sessions are
    not thread-safe, so each task opens (and always closes) its own.
    Never raises: a failure leaves the row untouched for the next tick.
    """
    from app.core.database import SessionLocal
    from app.services.news.translation_service import NewsTranslationService

    db = SessionLocal()
    try:
        service = NewsTranslationService(db)
        return service.auto_translate(article_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.info("auto-translate failed for %s: %s", article_id, exc)
        db.rollback()
        return {"article_id": article_id, "skipped": True, "reason": "error"}
    finally:
        db.close()


def auto_translate_for_ids(
    article_ids: list[int], *, time_budget_sec: int | None = None
) -> dict[str, int]:
    """Translate a batch of freshly-ingested articles, best-effort.

    Each article gets a title translation (when missing) and a body
    translation (when missing) via
    :meth:`NewsTranslationService.auto_translate`. The loop stops
    submitting new work when the time budget is exhausted — remaining
    rows are left for the drain job.

    Concurrency (2026-07-29): LLM calls are pure I/O wait (~12.6s per
    article serial for title+body), so the batch is fanned out over
    ``news_translation_concurrency`` worker threads. The old serial loop
    managed only ~285 articles/hour — below the ~240/hour non-Chinese
    inflow from the 652-source expansion, so the backlog grew without
    bound and unlucky rows (pushed out of the newest-first window)
    starved for days. 4 workers quadruple throughput on the same budget.
    """
    if not article_ids:
        return {"attempted": 0, "translated": 0, "skipped": 0, "budget_exhausted": 0}

    from app.config import get_settings

    settings = get_settings()
    if not settings.news_translation_on_ingest:
        return {"attempted": 0, "translated": 0, "skipped": 0, "budget_exhausted": 0}
    budget = time_budget_sec or settings.news_translation_ingest_time_budget_sec
    workers = max(1, settings.news_translation_concurrency)

    stats = {"attempted": 0, "translated": 0, "skipped": 0, "budget_exhausted": 0}
    started = time.monotonic()

    # Submit while the budget lasts; already-running tasks finish
    # normally (bounded by ``workers`` in-flight tasks). The per-task
    # LLM call has its own _MAX_LLM_CALL_SEC ceiling, so a hung call
    # can't stall the pool indefinitely.
    with ThreadPoolExecutor(
        max_workers=workers, thread_name_prefix="news-translate"
    ) as pool:
        futures = []
        for article_id in article_ids:
            if time.monotonic() - started > budget:
                stats["budget_exhausted"] = len(article_ids) - len(futures)
                break
            futures.append(pool.submit(_translate_one, article_id))

        for future in futures:
            stats["attempted"] += 1
            try:
                result = future.result()
            except Exception as exc:  # pragma: no cover - defensive
                logger.info("auto-translate worker raised: %s", exc)
                continue
            if result.get("skipped"):
                stats["skipped"] += 1
            elif result.get("translated") or result.get("title_new"):
                # Only NEW work counts: ``translated`` = fresh body
                # translation, ``title_new`` = fresh title translation.
                # A cached title/body must not inflate ``written`` —
                # that is how the drain reported 200/tick while making
                # zero progress (2026-07-31 poison-queue incident).
                stats["translated"] += 1

    if stats["translated"] or stats["budget_exhausted"]:
        logger.info("news auto-translate: %s", stats)
    return stats


def _pending_translation_ids(db, limit: int) -> list[int]:
    """Ids of non-Chinese articles still missing a translation.

    Newest first so recent headlines get Chinese titles quickly; the
    drain job then walks backwards into the archive one batch per tick.

    Poison-queue guards (2026-07-31):

    * **No-source-text rows are excluded.** ~200 excerpt-only rows
      (paywalled ``investing`` / ``seekingalpha`` items whose ``body``
      and ``full_content`` are both empty) can never get a body
      translation. Before this guard they sat permanently at the top
      of the newest-first window, consumed the whole batch every tick,
      and the 18.7k-row real backlog behind them was never touched.
      A row that still lacks ``title_zh`` is always kept — the title
      is translatable even without a body.
    * **Retry-capped rows are excluded.** Rows whose translation keeps
      failing increment ``translation_attempts``; at
      ``_MAX_TRANSLATION_ATTEMPTS`` (or immediately for deterministic
      MiniMax 422 "sensitive" rejections) they leave the window.
    """
    from app.services.news._model_loader import NewsArticle
    from app.services.news.translation_service import (
        _CHINESE_LANGUAGE_CODES,
        _MAX_TRANSLATION_ATTEMPTS,
    )

    has_source_text = or_(
        and_(NewsArticle.body.isnot(None), NewsArticle.body != ""),
        and_(
            NewsArticle.full_content.isnot(None),
            NewsArticle.full_content != "",
        ),
    )

    stmt = (
        select(NewsArticle.id)
        .where(
            # ``language`` is NOT NULL with default 'en' for the English
            # sources; the ``notin_`` guard keeps every Chinese variant out.
            NewsArticle.language.isnot(None),
            NewsArticle.language.notin_(sorted(_CHINESE_LANGUAGE_CODES)),
            NewsArticle.translation_attempts < _MAX_TRANSLATION_ATTEMPTS,
            or_(
                NewsArticle.title_zh.is_(None),
                and_(
                    NewsArticle.translated_zh.is_(None),
                    has_source_text,
                ),
                # Stale re-translation (2026-07-27): the cached translation
                # was made from the RSS excerpt and the full body arrived
                # afterwards — redo it so the reader gets the FULL Chinese
                # text, not a translated teaser.
                and_(
                    NewsArticle.translated_zh.isnot(None),
                    NewsArticle.full_content_fetched_at.isnot(None),
                    NewsArticle.translation_generated_at.isnot(None),
                    NewsArticle.full_content_fetched_at
                    > NewsArticle.translation_generated_at,
                ),
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
        # NOTE: the key must NOT be ``skipped`` — ``_record_etl`` treats
        # a truthy ``skipped`` as "whole run skipped" and zeroes
        # ``records_count``, hiding real progress from the health page.
        "skip_count": stats["skipped"],
    }
