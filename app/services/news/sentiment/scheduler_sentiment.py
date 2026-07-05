"""APScheduler jobs for the sentiment LLM pipeline.

Register with the existing ``app.core.scheduler.scheduler`` instance
via ``init_sentiment_jobs(scheduler)`` — called from ``init_scheduler``.

Cadence
-------

  every 30s  -  process up to 100 unprocessed articles (batch mode)
  every 5m   -  low-latency ingest of new articles from the last 5 min
  every 30m  -  retail aggregation for the top-50 hot symbols
  every 1h   -  cache hit-rate + cost snapshot (logged, not persisted)

We do **not** restart or replace the existing ``init_scheduler``; we
add jobs to the same APScheduler instance.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import desc

from app.core.database import SessionLocal
from app.core.redis_client import redis_lock
from app.models.research import SentimentData
from app.services.news.sentiment import SentimentPipeline, LLMPipelineMonitor
from app.services.news.sentiment.cache import SentimentCache

logger = logging.getLogger(__name__)

_LOCK_BATCH = "sentiment_batch"
_LOCK_RETAIL = "sentiment_retail_agg"


# ---------------------------------------------------------------------------
# Job callbacks (sync wrappers around async pipeline)
# ---------------------------------------------------------------------------


def _run_async(coro):
    """Bridge sync APScheduler callback -> async pipeline."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    if loop.is_running():
        # We're inside a running loop (e.g. in tests with pytest-asyncio).
        # Schedule the coroutine and return; APScheduler will still
        # tick again on the next interval.
        return asyncio.ensure_future(coro)
    return loop.run_until_complete(coro)


def run_sentiment_batch(limit: int = 100) -> int:
    """Process unprocessed articles in batch mode."""
    with redis_lock(_LOCK_BATCH, expire_seconds=600) as acquired:
        if not acquired:
            logger.info("[SentimentBatch] Skipped: lock in use")
            return 0

        db = SessionLocal()
        try:
            # Pick latest non-pipeline rows that don't already have a
            # parallel LLM-pipeline row.  The unique fingerprint is
            # (url, source='llm_pipeline') — we filter on url.
            recent = (
                db.query(SentimentData)
                .filter(SentimentData.source != "llm_pipeline")
                .order_by(desc(SentimentData.ingested_at))
                .limit(limit)
                .all()
            )
            articles = [
                {
                    "url": r.url or f"sentiment:{r.id}",
                    "title": r.title or "",
                    "body": r.content or "",
                    "published_at": r.published_at,
                }
                for r in recent
                if r.url
            ]
            if not articles:
                return 0

            pipe = SentimentPipeline(db)

            async def _go():
                return await pipe.process_batch(articles, concurrency=10)

            results = _run_async(_go())
            ok = sum(1 for r in results if r.success)
            logger.info(
                "[SentimentBatch] processed=%d success=%d cache_hits=%d",
                len(results),
                ok,
                sum(1 for r in results if r.cache_hit),
            )
            return ok
        finally:
            db.close()


def run_sentiment_low_latency(window_minutes: int = 5) -> int:
    """Re-process anything ingested in the last ``window_minutes``."""
    with redis_lock(f"{_LOCK_BATCH}_lowlat", expire_seconds=300) as acquired:
        if not acquired:
            return 0
        db = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
            recent = (
                db.query(SentimentData)
                .filter(SentimentData.ingested_at >= cutoff)
                .filter(SentimentData.source != "llm_pipeline")
                .order_by(desc(SentimentData.ingested_at))
                .limit(50)
                .all()
            )
            articles = [
                {
                    "url": r.url or f"sentiment:{r.id}",
                    "title": r.title or "",
                    "body": r.content or "",
                    "published_at": r.published_at,
                }
                for r in recent
                if r.url
            ]
            if not articles:
                return 0
            pipe = SentimentPipeline(db)

            async def _go():
                return await pipe.process_batch(articles, concurrency=5)

            results = _run_async(_go())
            return sum(1 for r in results if r.success)
        finally:
            db.close()


def run_news_article_categorization(limit: int = 30) -> int:
    """Categorize recent ``news_article`` rows that lack ``event_category``.

    This job wires the LLM sentiment pipeline directly to the crawler-
    generated ``news_article`` table so that geopolitics / central_bank /
    election / trade_war / sanction categories are populated for the
    Global Markets page and downstream event-driven strategies.
    """
    with redis_lock(f"{_LOCK_BATCH}_news", expire_seconds=600) as acquired:
        if not acquired:
            logger.info("[NewsArticleCategorization] Skipped: lock in use")
            return 0
        db = SessionLocal()
        try:
            from app.services.news._model_loader import NewsArticle

            recent = (
                db.query(NewsArticle)
                .filter(NewsArticle.event_category.is_(None))
                .order_by(desc(NewsArticle.published_at))
                .limit(limit)
                .all()
            )
            articles = [
                {
                    "id": r.id,
                    "url": r.url or f"news:{r.id}",
                    "title": r.title or "",
                    "body": r.body or r.summary or "",
                    "published_at": r.published_at,
                }
                for r in recent
            ]
            if not articles:
                return 0

            pipe = SentimentPipeline(db)

            async def _go():
                return await pipe.process_batch(articles, concurrency=5)

            results = _run_async(_go())
            ok = sum(1 for r in results if r.success)
            logger.info(
                "[NewsArticleCategorization] processed=%d success=%d cache_hits=%d",
                len(results),
                ok,
                sum(1 for r in results if r.cache_hit),
            )
            return ok
        finally:
            db.close()


def run_retail_aggregation(top_n: int = 50) -> int:
    """Aggregate retail chatter for the top hot symbols.

    Retail comment gathering is a future Agent's job; this job is
    a no-op when no comments are present in any future
    ``retail_comment`` table.  Until then it just refreshes the
    hot-symbols zset from the watch-list so other consumers see it.
    """
    with redis_lock(_LOCK_RETAIL, expire_seconds=900) as acquired:
        if not acquired:
            return 0
        cache = SentimentCache()
        # For now, derive hot symbols from the most-mentioned instruments
        # in the last 24h.
        db = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(hours=24)
            hot_rows = (
                db.query(SentimentData.instrument_code)
                .filter(SentimentData.ingested_at >= cutoff)
                .filter(SentimentData.instrument_code.isnot(None))
                .group_by(SentimentData.instrument_code)
                .order_by(desc(SentimentData.id))
                .limit(top_n)
                .all()
            )
            for (sym,) in hot_rows:
                if not sym:
                    continue
                cache.add_hot_symbol(sym, 1)
            return len(hot_rows)
        finally:
            db.close()


def run_daily_cost_snapshot() -> dict:
    """Hourly summary log; nightly flush to DB at 00:05 Asia/Shanghai."""
    snap = LLMPipelineMonitor().daily_summary()
    logger.info(
        "[SentimentCost] day=%s calls=%d cost=%.4f hit_rate=%.2f",
        snap.get("date"),
        snap.get("total_calls", 0),
        snap.get("total_cost_usd", 0.0),
        snap.get("cache_hit_rate", 0.0),
    )
    return snap


def run_nightly_flush() -> dict:
    """00:05 local time — flush yesterday's counters to llm_usage_daily."""
    yesterday = date.today() - timedelta(days=1)
    snap = LLMPipelineMonitor().daily_summary(yesterday)
    logger.info(
        "[SentimentFlush] flushed day=%s cost=%.4f",
        snap.get("date"),
        snap.get("total_cost_usd", 0.0),
    )
    return snap


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def init_sentiment_jobs(scheduler: BackgroundScheduler) -> None:
    """Register all sentiment-pipeline jobs on the given scheduler."""
    scheduler.add_job(
        run_sentiment_batch,
        trigger=IntervalTrigger(seconds=30),
        id="sentiment_batch_30s",
        name="情绪批量处理-30秒",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_sentiment_low_latency,
        trigger=IntervalTrigger(minutes=5),
        id="sentiment_low_latency_5m",
        name="情绪低延迟处理-5分钟",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_news_article_categorization,
        trigger=IntervalTrigger(minutes=1),
        id="news_article_categorization_1m",
        name="新闻事件分类-1分钟",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_retail_aggregation,
        trigger=IntervalTrigger(minutes=30),
        id="sentiment_retail_agg_30m",
        name="散户讨论聚合-30分钟",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_daily_cost_snapshot,
        trigger=IntervalTrigger(hours=1),
        id="sentiment_cost_snapshot_1h",
        name="情绪成本快照-1小时",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_nightly_flush,
        trigger=CronTrigger(hour=0, minute=5, timezone="Asia/Shanghai"),
        id="sentiment_nightly_flush",
        name="情绪成本日终落库-00:05",
        replace_existing=True,
        max_instances=1,
    )
    logger.info("[SentimentScheduler] jobs registered")
