"""Synchronous wrappers for async news crawlers.

Each wrapper is a thin facade that runs an async crawl and persists
results. The actual crawlers (xinhua/cninfo/sina/yahoo/cnbc/sec/reddit/
coindesk/cointelegraph) expose an async ``crawl()`` method; this module
adds a thin DB-write layer and exposes a sync function suitable for
APScheduler.

Every wrapper also writes a row to ``etl_log`` so the news-health
endpoint can show real run history (start/end, status, record count,
any error). The mapping between wrapper function and scheduler job id
is fixed by the APScheduler registrations in
``app.core.scheduler``; the wrapper bakes the id in via the
``@_record_etl`` decorator so callers don't have to thread it through.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Any

from app.core.etl_log_helper import record_etl
from app.models.etl import ETLLog

logger = logging.getLogger(__name__)


def _run_async(coro: Any) -> Any:
    """Run an async coroutine on a reused event loop."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _record_etl(job_id: str) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
    """Decorator that persists a start/finish ``ETLLog`` row.

    The wrapper's return value must be a dict; we use ``written`` (or
    the smaller of ``fetched``/``written``) as the record count and
    treat a missing/zero result as success. If the wrapped function
    raises we record ``status="failed"`` with the exception message,
    swallowing any DB error so the scheduler does not crash.
    """
    def decorator(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            from app.core.database import SessionLocal

            db = SessionLocal()
            log_row: ETLLog | None = None
            started = time.monotonic()
            try:
                log_row = ETLLog(
                    job_name=job_id,
                    status="running",
                    start_time=datetime.now(UTC),
                )
                db.add(log_row)
                db.commit()
                db.refresh(log_row)
            except Exception as exc:  # pragma: no cover - best effort
                logger.debug("etl_log start insert failed for %s: %s", job_id, exc)
                # Continue without a log row — never block the tick.

            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                # Update the log row we created (if any), then re-raise
                # so the existing scheduler behaviour (logged + empty
                # return) is preserved.
                try:
                    if log_row is not None:
                        log_row.status = "failed"
                        log_row.end_time = datetime.now(UTC)
                        log_row.records_count = 0
                        log_row.error_msg = str(exc)[:1000]
                        db.commit()
                except Exception:  # pragma: no cover - defensive
                    with contextlib.suppress(Exception):
                        db.rollback()
                finally:
                    db.close()
                raise

            # Successful return path.
            try:
                if log_row is not None:
                    log_row.status = "success"
                    log_row.end_time = datetime.now(UTC)
                    records = int(
                        result.get("written")
                        if isinstance(result, dict) and result.get("written") is not None
                        else (result.get("fetched") if isinstance(result, dict) else 0)
                        or 0
                    )
                    # ``skipped`` ticks (e.g. reddit without
                    # credentials) record as success with 0 records +
                    # a note in ``extra_data`` so the health page can
                    # distinguish "not configured" from "running fine".
                    if isinstance(result, dict) and result.get("skipped"):
                        log_row.status = "skipped"
                        log_row.records_count = 0
                        log_row.extra_data = {
                            "reason": result.get("skip_reason") or "skipped",
                            "duration_seconds": round(time.monotonic() - started, 3),
                        }
                    else:
                        log_row.records_count = records
                        log_row.extra_data = {
                            "duration_seconds": round(time.monotonic() - started, 3),
                        }
                    db.commit()
            except Exception as exc:  # pragma: no cover - best effort
                logger.debug("etl_log finish update failed for %s: %s", job_id, exc)
                with contextlib.suppress(Exception):
                    db.rollback()
            finally:
                db.close()
            return result

        return wrapper

    return decorator


# Small default universe for sources that need a ticker list.
_DEFAULT_US_TICKERS = [
    "AAPL", "TSLA", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "AMD",
    "INTC", "BABA", "NFLX", "JPM", "V", "WMT", "DIS", "KO", "PFE",
]

# Minimal CIK map for SEC EDGAR filings crawler.
_SEC_EDGAR_TICKER_TO_CIK: dict[str, str | int] = {
    "AAPL": "320193",
    "MSFT": "789019",
    "AMZN": "1018724",
    "GOOGL": "1652044",
    "META": "1326801",
    "TSLA": "1318605",
    "NVDA": "1045810",
    "AMD": "2488",
    "INTC": "50863",
    "BABA": "1577552",
    "NFLX": "1065280",
    "JPM": "19617",
    "V": "1403161",
    "WMT": "104169",
    "DIS": "1744489",
}


def _write_to_db(articles: list) -> int:
    """Persist RawArticles into NewsArticle via the normalizer."""
    if not articles:
        return 0
    from app.core.database import SessionLocal
    from app.services.news.normalizer import NewsNormalizer

    db = SessionLocal()
    try:
        normalizer = NewsNormalizer(db)
        written = 0
        new_ids: list[int] = []
        for raw in articles:
            try:
                article = normalizer.normalize(raw)
                if article is not None:
                    written += 1
                    new_ids.append(article.id)
            except Exception as exc:  # pragma: no cover
                logger.warning("normalizer failed for %s: %s", raw.url, exc)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("DB commit failed: %s", exc)
        return 0
    finally:
        db.close()

    # Ingest-time full-content fetch (2026-07-21): grab the cleaned body
    # right away so the detail page renders it immediately. Bounded by
    # ``news_content_ingest_time_budget_sec`` and fully fail-safe — the
    # 10-minute scheduler job drains whatever is left.
    if new_ids:
        from app.services.news.scheduler_fetch_full_content import (
            fetch_full_content_for_ids,
        )

        fetch_full_content_for_ids(new_ids)

        # Ingest-time auto translation (2026-07-26): translate title +
        # body of non-Chinese articles to Chinese right after the body
        # is available, so list/detail pages render Chinese-first.
        # Bounded by ``news_translation_ingest_time_budget_sec``; the
        # 10-minute ``news_translate_10m`` drain job covers the rest.
        from app.services.news.scheduler_translate_news import (
            auto_translate_for_ids,
        )

        auto_translate_for_ids(new_ids)
    return written


# ── A-share ──

def run_xinhua_crawl() -> dict[str, int]:
    # NOTE: xinhua RSS endpoints are currently 404; the cron job in
    # ``app.core.scheduler`` is disabled. The function is preserved
    # so callers that wire it explicitly still work, but we skip the
    # @_record_etl decorator since there is no scheduler job id.
    from app.services.news.sources.xinhua import XinhuaCrawler

    async def _go():
        async with XinhuaCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("xinhua crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


@_record_etl("news_cninfo_10m")
def run_cninfo_crawl() -> dict[str, int]:
    from app.services.news.sources.cninfo import CninfoCrawler

    async def _go():
        async with CninfoCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("cninfo crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


@_record_etl("news_sina_5m")
def run_sina_crawl() -> dict[str, int]:
    from app.services.news.sources.sina import SinaCrawler

    async def _go():
        async with SinaCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("sina crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


# ── WeChat (wewe-rss) ──

def _build_marketing_filter(source: str, *, english: bool = False) -> Any | None:
    """Build a :class:`MarketingContentFilter`, fail-open to ``None``.

    A construction failure must never block the crawl — ``None`` tells
    :func:`_apply_marketing_filter` to pass every article through.
    ``english=True`` selects the English system-prompt variant for
    English-language self-media sources (zerohedge, decrypt).
    """
    try:
        from app.services.news.filters.marketing_filter import (
            DEFAULT_SYSTEM_PROMPT_EN,
            MarketingContentFilter,
        )

        return MarketingContentFilter(
            source=source,
            system_prompt=DEFAULT_SYSTEM_PROMPT_EN if english else None,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "%s marketing filter init failed, passing through: %s", source, exc
        )
        return None


def _apply_marketing_filter(articles: list, marketing_filter: Any | None) -> tuple[list, int]:
    """Run the two-step marketing filter over a batch of articles.

    Returns ``(kept, rejected_count)``. The verdict is stashed in
    ``extra["marketing_verdict"]`` / ``extra["marketing_confidence"]``
    for downstream debugging / health-page telemetry. A ``None`` filter
    (construction failed) passes everything through.
    """
    kept: list = []
    rejected = 0
    for art in articles:
        if marketing_filter is None:
            kept.append(art)
            continue
        verdict = marketing_filter.classify(art.title, art.body)
        if verdict.is_knowledge:
            art.extra = dict(art.extra or {})
            art.extra["marketing_verdict"] = verdict.reason
            art.extra["marketing_confidence"] = verdict.confidence
            kept.append(art)
        else:
            rejected += 1
    return kept, rejected


@_record_etl("news_wechat_zeping_15m")
def run_wechat_zeping_crawl() -> dict[str, int]:
    """Poll wewe-rss for the configured WeChat accounts.

    Always silent when wewe-rss is unreachable (returns
    ``fetched=0, written=0``); the ``_record_etl`` wrapper still
    records the run so the health page shows the failure mode. The
    marketing filter runs synchronously inside this tick — it caches
    LLM verdicts for 24h so a 15-minute poll doesn't repeatedly bill
    the LLM for the same posts. The filter classifies per article, so
    posts from multiple feeds (``wechat_rss_feed_map``) with distinct
    per-feed source names are all covered.
    """
    from app.services.news.filters import WechatMarketingFilter
    from app.services.news.sources.wechat_zeping import WechatZepingCrawler

    async def _go():
        crawler = WechatZepingCrawler()
        return await crawler.fetch_recent(limit=30)

    try:
        articles = _run_async(_go())
    except Exception as exc:
        logger.exception("wechat crawl failed: %s", exc)
        return {
            "fetched": 0,
            "written": 0,
            "skipped": True,
            "skip_reason": f"crawl_error: {exc}",
        }

    if not articles:
        # Empty list either means wewe-rss is down or no feed ids are
        # configured yet. Either way the scheduler should treat this as
        # a no-op rather than an error.
        return {"fetched": 0, "written": 0, "skipped": True, "skip_reason": "no_articles"}

    try:
        marketing_filter = WechatMarketingFilter()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("wechat marketing filter init failed, passing through: %s", exc)
        marketing_filter = None

    filtered, rejected = _apply_marketing_filter(articles, marketing_filter)

    written = _write_to_db(filtered)
    return {
        "fetched": len(articles),
        "written": written,
        "rejected_marketing": rejected,
    }


# ── wechat2rss public-mirror batches (added 2026-07-27) ──
#
# 41 hand-picked independent WeChat accounts served by the public
# wechat2rss mirror, split into 4 batch jobs (~10 feeds each) so the
# scheduler gains only 4 jobs instead of 41. See
# app/services/news/sources/wechat2rss_batch.py for the selection rule.


def _wechat2rss_batch_job(job_id: str, batch_key: str):
    """Build a ``run_*`` function crawling one wechat2rss batch."""

    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        from app.services.news.filters import WechatMarketingFilter
        from app.services.news.sources.wechat2rss_batch import (
            Wechat2RssBatchCrawler,
        )

        async def _go():
            crawler = Wechat2RssBatchCrawler(batch_key)
            return await crawler.fetch_recent()

        try:
            articles = _run_async(_go())
        except Exception as exc:
            logger.exception("wechat2rss batch %s crawl failed: %s", batch_key, exc)
            return {
                "fetched": 0,
                "written": 0,
                "skipped": True,
                "skip_reason": f"crawl_error: {exc}",
            }

        if not articles:
            return {"fetched": 0, "written": 0, "skipped": True, "skip_reason": "no_articles"}

        try:
            marketing_filter = WechatMarketingFilter()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("wechat marketing filter init failed, passing through: %s", exc)
            marketing_filter = None

        filtered, rejected = _apply_marketing_filter(articles, marketing_filter)
        written = _write_to_db(filtered)
        return {
            "fetched": len(articles),
            "written": written,
            "rejected_marketing": rejected,
        }

    _run.__name__ = f"run_wechat2rss_{batch_key}_crawl"
    return _run


WECHAT2RSS_BATCH_JOBS: list[tuple[str, str, str]] = [
    # (job_id, label, batch_key) — all run every 60 minutes.
    ("news_wechat2rss_a_60m", "公众号镜像 A 组", "a"),
    ("news_wechat2rss_b_60m", "公众号镜像 B 组", "b"),
    ("news_wechat2rss_c_60m", "公众号镜像 C 组", "c"),
    ("news_wechat2rss_d_60m", "公众号镜像 D 组", "d"),
    ("news_wechat2rss_e_60m", "公众号镜像 E 组", "e"),
    ("news_wechat2rss_f_60m", "公众号镜像 F 组", "f"),
    ("news_wechat2rss_g_60m", "公众号镜像 G 组", "g"),
    ("news_wechat2rss_h_60m", "公众号镜像 H 组", "h"),
    ("news_wechat2rss_i_60m", "公众号镜像 I 组", "i"),
]
for _job_id, _label, _batch in WECHAT2RSS_BATCH_JOBS:
    globals()[f"run_wechat2rss_{_batch}_crawl"] = _wechat2rss_batch_job(_job_id, _batch)


# ── wechat2rss second-wave batches (added 2026-07-28) ──
#
# 103 more WeChat accounts — macro / strategy / industry / tech /
# business — served by TWO public wechat2rss mirrors (bestblogs.dev
# self-hosted instance + the original xlab.app free list). Table and
# selection rule live in
# app/services/news/sources/wechat2rss_batch2.py; evidence table in
# docs/dev-notes/20260728-wechat-batch2.md. Same batching rationale
# as the first wave (10 jobs for 103 feeds, keys w2a-w2j). The
# marketing filter stays on: this wave includes portal-media and
# review accounts where soft-ad posts do appear.


def _wechat2b_batch_job(job_id: str, batch_key: str):
    """Build a ``run_*`` function crawling one second-wave wechat2rss batch."""

    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        from app.services.news.filters import WechatMarketingFilter
        from app.services.news.sources.wechat2rss_batch2 import (
            Wechat2RssBatch2Crawler,
        )

        async def _go():
            crawler = Wechat2RssBatch2Crawler(batch_key)
            return await crawler.fetch_recent()

        try:
            articles = _run_async(_go())
        except Exception as exc:
            logger.exception("wechat2rss batch2 %s crawl failed: %s", batch_key, exc)
            return {
                "fetched": 0,
                "written": 0,
                "skipped": True,
                "skip_reason": f"crawl_error: {exc}",
            }

        if not articles:
            return {"fetched": 0, "written": 0, "skipped": True, "skip_reason": "no_articles"}

        try:
            marketing_filter = WechatMarketingFilter()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("wechat marketing filter init failed, passing through: %s", exc)
            marketing_filter = None

        filtered, rejected = _apply_marketing_filter(articles, marketing_filter)
        written = _write_to_db(filtered)
        return {
            "fetched": len(articles),
            "written": written,
            "rejected_marketing": rejected,
        }

    _run.__name__ = f"run_wechat2b_{batch_key}_crawl"
    return _run


WECHAT2B_BATCH_JOBS: list[tuple[str, str, str]] = [
    # (job_id, label, batch_key) — all run every 60 minutes.
    ("news_wechat2b_w2a_60m", "公众号二批 A 组", "w2a"),
    ("news_wechat2b_w2b_60m", "公众号二批 B 组", "w2b"),
    ("news_wechat2b_w2c_60m", "公众号二批 C 组", "w2c"),
    ("news_wechat2b_w2d_60m", "公众号二批 D 组", "w2d"),
    ("news_wechat2b_w2e_60m", "公众号二批 E 组", "w2e"),
    ("news_wechat2b_w2f_60m", "公众号二批 F 组", "w2f"),
    ("news_wechat2b_w2g_60m", "公众号二批 G 组", "w2g"),
    ("news_wechat2b_w2h_60m", "公众号二批 H 组", "w2h"),
    ("news_wechat2b_w2i_60m", "公众号二批 I 组", "w2i"),
    ("news_wechat2b_w2j_60m", "公众号二批 J 组", "w2j"),
]
for _job_id, _label, _batch in WECHAT2B_BATCH_JOBS:
    globals()[f"run_wechat2b_{_batch}_crawl"] = _wechat2b_batch_job(_job_id, _batch)


# ── wechat2rss third-wave batches (added 2026-07-29) ──
#
# 22 more WeChat accounts — geo-economics / strategy / industry
# (consumer / gaming / finance-workplace) / tech commentary / depth
# journalism — all served by the bestblogs.dev public wechat2rss
# mirror (the xlab mirror's qualified pool was exhausted by waves
# 1/2; re-verified 2026-07-29, zero additions). Table, batching and
# job metadata live in
# app/services/news/sources/wechat2rss_batch3.py; evidence table in
# docs/dev-notes/20260729-wechat-batch3.md. The marketing filter
# stays on: this wave includes portal/weekly media where soft-ad
# posts do appear.


def _wechat3_batch_job(job_id: str, batch_key: str):
    """Build a ``run_*`` function crawling one third-wave wechat2rss batch."""

    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        from app.services.news.filters import WechatMarketingFilter
        from app.services.news.sources.wechat2rss_batch3 import (
            Wechat2RssBatch3Crawler,
        )

        async def _go():
            crawler = Wechat2RssBatch3Crawler(batch_key)
            return await crawler.fetch_recent()

        try:
            articles = _run_async(_go())
        except Exception as exc:
            logger.exception("wechat2rss batch3 %s crawl failed: %s", batch_key, exc)
            return {
                "fetched": 0,
                "written": 0,
                "skipped": True,
                "skip_reason": f"crawl_error: {exc}",
            }

        if not articles:
            return {"fetched": 0, "written": 0, "skipped": True, "skip_reason": "no_articles"}

        try:
            marketing_filter = WechatMarketingFilter()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("wechat marketing filter init failed, passing through: %s", exc)
            marketing_filter = None

        filtered, rejected = _apply_marketing_filter(articles, marketing_filter)
        written = _write_to_db(filtered)
        return {
            "fetched": len(articles),
            "written": written,
            "rejected_marketing": rejected,
        }

    _run.__name__ = f"run_wechat3_{batch_key}_crawl"
    return _run


from app.services.news.sources.wechat2rss_batch3 import (  # noqa: E402
    WECHAT3_BATCH_JOBS,
)

for _job_id, _label, _batch in WECHAT3_BATCH_JOBS:
    globals()[f"run_wechat3_{_batch}_crawl"] = _wechat3_batch_job(_job_id, _batch)


# ── Global multi-language RSS batches (added 2026-07-27) ──

#
# 125 live-verified feeds — Japanese / German / French / Korean /
# Spanish publications, a second wave of English central-bank /
# think-tank / university / engineering blogs, and Chinese non-blog
# industry press — split into 12 batch jobs (11 feeds each) so the
# scheduler gains 12 jobs instead of 125. See
# app/services/news/sources/global_rss_batch.py for the selection rule.


def _global_rss_batch_job(job_id: str, batch_key: str):
    """Build a ``run_*`` function crawling one global-RSS batch."""

    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        from app.services.news.sources.global_rss_batch import (
            GlobalRssBatchCrawler,
        )

        async def _go():
            crawler = GlobalRssBatchCrawler(batch_key)
            return await crawler.fetch_recent()

        try:
            articles = _run_async(_go())
        except Exception as exc:
            logger.exception("global rss batch %s crawl failed: %s", batch_key, exc)
            return {
                "fetched": 0,
                "written": 0,
                "skipped": True,
                "skip_reason": f"crawl_error: {exc}",
            }

        if not articles:
            return {"fetched": 0, "written": 0, "skipped": True, "skip_reason": "no_articles"}

        # No marketing filter: these are professional publications and
        # research/engineering blogs, not ad-driven self-media (unlike
        # the WeChat accounts). Mirrors ``_simple_rss_job``.
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}

    _run.__name__ = f"run_global_rss_{batch_key}_crawl"
    return _run


GLOBAL_RSS_BATCH_JOBS: list[tuple[str, str, str]] = [
    # (job_id, label, batch_key) — all run every 60 minutes.
    ("news_global_rss_a_60m", "全球多语 RSS A 组", "a"),
    ("news_global_rss_b_60m", "全球多语 RSS B 组", "b"),
    ("news_global_rss_c_60m", "全球多语 RSS C 组", "c"),
    ("news_global_rss_d_60m", "全球多语 RSS D 组", "d"),
    ("news_global_rss_e_60m", "全球多语 RSS E 组", "e"),
    ("news_global_rss_f_60m", "全球多语 RSS F 组", "f"),
    ("news_global_rss_g_60m", "全球多语 RSS G 组", "g"),
    ("news_global_rss_h_60m", "全球多语 RSS H 组", "h"),
    ("news_global_rss_i_60m", "全球多语 RSS I 组", "i"),
    ("news_global_rss_j_60m", "全球多语 RSS J 组", "j"),
    ("news_global_rss_k_60m", "全球多语 RSS K 组", "k"),
    ("news_global_rss_l_60m", "全球多语 RSS L 组", "l"),
]
for _job_id, _label, _batch in GLOBAL_RSS_BATCH_JOBS:
    globals()[f"run_global_rss_{_batch}_crawl"] = _global_rss_batch_job(_job_id, _batch)


# ── Asia-focused English RSS batches (added 2026-07-28) ──
#
# 176 live-verified English feeds — Asian English financial media
# (India/SEA/South Asia/Gulf/Central Asia/China-EN/AU-NZ),
# international media section feeds beyond the front page, industry
# verticals (semiconductors, new energy, biopharma, automotive,
# shipping & logistics, commodities & mining, aerospace/defense/
# fintech trades) and self-hosted investor blogs — split into 16
# batch jobs (11 feeds each) so the scheduler gains 16 jobs instead
# of 176. See app/services/news/sources/asia_en_batch.py for the
# selection rule and docs/dev-notes/20260728-asia-en-batch.md for the
# two-round ECS verification evidence.

from app.services.news.sources.asia_en_batch import (  # noqa: E402
    ASIA_EN_BATCH_JOBS,
)


def _asia_en_batch_job(job_id: str, batch_key: str):
    """Build a ``run_*`` function crawling one Asia-EN batch."""

    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        from app.services.news.sources.asia_en_batch import (
            AsiaEnBatchCrawler,
        )

        async def _go():
            crawler = AsiaEnBatchCrawler(batch_key)
            return await crawler.fetch_recent()

        try:
            articles = _run_async(_go())
        except Exception as exc:
            logger.exception("asia-en batch %s crawl failed: %s", batch_key, exc)
            return {
                "fetched": 0,
                "written": 0,
                "skipped": True,
                "skip_reason": f"crawl_error: {exc}",
            }

        if not articles:
            return {"fetched": 0, "written": 0, "skipped": True, "skip_reason": "no_articles"}

        # No marketing filter: professional publications and curated
        # blogs, same precedent as ``_global_rss_batch_job``.
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}

    _run.__name__ = f"run_asia_en_{batch_key}_crawl"
    return _run


for _job_id, _label, _batch in ASIA_EN_BATCH_JOBS:
    globals()[f"run_asia_en_{_batch}_crawl"] = _asia_en_batch_job(_job_id, _batch)



# ── Independent non-WeChat batches (added 2026-07-28) ──
#
# 144 verified independent blogs / newsletters / podcasts (English +
# Chinese) — no official media, no corporate PR. Table and selection
# rule live in app/services/news/sources/independent_batch.py. Same
# batching rationale as the wechat2rss mirror above (~11 feeds per
# hourly job). Unlike the WeChat batches these jobs skip the LLM
# marketing filter — the sources are curated editorial voices (same
# precedent as INDEPENDENT_RSS_JOBS), and skipping keeps LLM cost flat.

def _independent_batch_job(job_id: str, batch_key: str):
    """Build a ``run_*`` function crawling one independent-source batch."""

    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        from app.services.news.sources.independent_batch import (
            IndependentBatchCrawler,
        )

        async def _go():
            crawler = IndependentBatchCrawler(batch_key)
            return await crawler.fetch_recent()

        try:
            articles = _run_async(_go())
        except Exception as exc:
            logger.exception("independent batch %s crawl failed: %s", batch_key, exc)
            return {
                "fetched": 0,
                "written": 0,
                "skipped": True,
                "skip_reason": f"crawl_error: {exc}",
            }

        if not articles:
            return {"fetched": 0, "written": 0, "skipped": True, "skip_reason": "no_articles"}

        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}

    _run.__name__ = f"run_independent_{batch_key}_crawl"
    return _run


INDEPENDENT_BATCH_JOBS: list[tuple[str, str, str]] = [
    # (job_id, label, batch_key) — all run every 60 minutes.
    ("news_indie_a_60m", "独立源 A 组", "a"),
    ("news_indie_b_60m", "独立源 B 组", "b"),
    ("news_indie_c_60m", "独立源 C 组", "c"),
    ("news_indie_d_60m", "独立源 D 组", "d"),
    ("news_indie_e_60m", "独立源 E 组", "e"),
    ("news_indie_f_60m", "独立源 F 组", "f"),
    ("news_indie_g_60m", "独立源 G 组", "g"),
    ("news_indie_h_60m", "独立源 H 组", "h"),
    ("news_indie_i_60m", "独立源 I 组", "i"),
    ("news_indie_j_60m", "独立源 J 组", "j"),
    ("news_indie_k_60m", "独立源 K 组", "k"),
    ("news_indie_l_60m", "独立源 L 组", "l"),
    ("news_indie_m_60m", "独立源 M 组", "m"),
    ("news_indie_n_60m", "独立源 N 组", "n"),
]
for _job_id, _label, _batch in INDEPENDENT_BATCH_JOBS:
    globals()[f"run_independent_{_batch}_crawl"] = _independent_batch_job(_job_id, _batch)


# ── Global English indie batches (added 2026-07-28) ──
#
# 104 live-verified English independent blogs / newsletters / research
# outlets (custom-domain Substacks, Ghost, dev.to/Hashnode authors,
# nonprofit newsrooms). Table and selection rule live in
# app/services/news/sources/global_indie_batch.py; batch keys o-x keep
# clear of the a-n keys owned by INDEPENDENT_BATCH_JOBS. Same no-LLM
# rationale as the independent batches (curated editorial voices).

def _global_indie_batch_job(job_id: str, batch_key: str):
    """Build a ``run_*`` function crawling one global-indie batch."""

    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        from app.services.news.sources.global_indie_batch import (
            GlobalIndieBatchCrawler,
        )

        async def _go():
            crawler = GlobalIndieBatchCrawler(batch_key)
            return await crawler.fetch_recent()

        try:
            articles = _run_async(_go())
        except Exception as exc:
            logger.exception("global indie batch %s crawl failed: %s", batch_key, exc)
            return {
                "fetched": 0,
                "written": 0,
                "skipped": True,
                "skip_reason": f"crawl_error: {exc}",
            }

        if not articles:
            return {"fetched": 0, "written": 0, "skipped": True, "skip_reason": "no_articles"}

        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}

    _run.__name__ = f"run_global_indie_{batch_key}_crawl"
    return _run


from app.services.news.sources.global_indie_batch import (  # noqa: E402
    GLOBAL_INDIE_BATCH_JOBS,
)

for _job_id, _label, _batch in GLOBAL_INDIE_BATCH_JOBS:
    globals()[f"run_global_indie_{_batch}_crawl"] = _global_indie_batch_job(_job_id, _batch)


# ── Chinese podcast batches (added 2026-07-29) ──
#
# 40 live-verified Chinese-language podcasts (investing / macro /
# business analysis / industry depth / tech commentary) on 小宇宙 /
# 喜马拉雅 / SoundOn / Firstory / Fireside / Acast / SoundCloud /
# self-hosted feeds. Table and selection rule live in
# app/services/news/sources/zh_multi_batch.py; batch keys a-d sit in
# their own job namespace (news_zhx_*), so they do not collide with
# the a-n (independent) / o-x (global indie) key ranges. Same no-LLM
# rationale as the independent batches (curated editorial voices) —
# no marketing filter.

def _zhx_batch_job(job_id: str, batch_key: str):
    """Build a ``run_*`` function crawling one Chinese podcast batch."""

    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        from app.services.news.sources.zh_multi_batch import (
            ZhMultiBatchCrawler,
        )

        async def _go():
            crawler = ZhMultiBatchCrawler(batch_key)
            return await crawler.fetch_recent()

        try:
            articles = _run_async(_go())
        except Exception as exc:
            logger.exception("zh podcast batch %s crawl failed: %s", batch_key, exc)
            return {
                "fetched": 0,
                "written": 0,
                "skipped": True,
                "skip_reason": f"crawl_error: {exc}",
            }

        if not articles:
            return {"fetched": 0, "written": 0, "skipped": True, "skip_reason": "no_articles"}

        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}

    _run.__name__ = f"run_zh_multi_{batch_key}_crawl"
    return _run


from app.services.news.sources.zh_multi_batch import (  # noqa: E402
    ZH_MULTI_BATCH_JOBS,
)

for _job_id, _label, _batch in ZH_MULTI_BATCH_JOBS:
    globals()[f"run_zh_multi_{_batch}_crawl"] = _zhx_batch_job(_job_id, _batch)


# ── Chinese blog batches (added 2026-07-30) ──
#
# 38 live-verified Chinese-language blogs / independent commentary
# sites / Chinese international media / curated community feeds — the
# final wave (D1) of the ">=100 中文圈独立思考资讯源" push. Table and
# selection rule live in app/services/news/sources/zh_blog_batch.py;
# batch keys a-d sit in their own job namespace (news_zhb_*). Same
# no-LLM rationale as the other batch waves (curated editorial
# voices) — no marketing filter.

def _zhb_batch_job(job_id: str, batch_key: str):
    """Build a ``run_*`` function crawling one Chinese blog batch."""

    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        from app.services.news.sources.zh_blog_batch import (
            ZhBlogBatchCrawler,
        )

        async def _go():
            crawler = ZhBlogBatchCrawler(batch_key)
            return await crawler.fetch_recent()

        try:
            articles = _run_async(_go())
        except Exception as exc:
            logger.exception("zh blog batch %s crawl failed: %s", batch_key, exc)
            return {
                "fetched": 0,
                "written": 0,
                "skipped": True,
                "skip_reason": f"crawl_error: {exc}",
            }

        if not articles:
            return {"fetched": 0, "written": 0, "skipped": True, "skip_reason": "no_articles"}

        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}

    _run.__name__ = f"run_zh_blog_{batch_key}_crawl"
    return _run


from app.services.news.sources.zh_blog_batch import (  # noqa: E402
    ZH_BLOG_BATCH_JOBS,
)

for _job_id, _label, _batch in ZH_BLOG_BATCH_JOBS:
    globals()[f"run_zh_blog_{_batch}_crawl"] = _zhb_batch_job(_job_id, _batch)


# ── English finance media / macro blog batches (added 2026-08-02) ──
#
# 57 live-verified English feeds — US/UK broadcast & print finance
# desks (CNBC desks, NYT, Economist, FT Alphaville…), investment
# industry & alternatives trades, international English outlets,
# emerging-market English media, macro/analysis Substacks & blogs and
# a handful of official-sector feeds (Fed testimony, BOJ). Table and
# ECS verification evidence live in
# app/services/news/sources/en_fin_batch.py. 6 feeds (fedspeeches /
# fedmonetary / cbo / cato / cfodive / paymentsdive) were collected by
# both this wave and the official wave — they live in
# official_batch.py only. Same no-LLM rationale as the other batch
# waves.

from app.services.news.sources.en_fin_batch import (  # noqa: E402
    EN_FIN_BATCH_JOBS,
)


def _enf_batch_job(job_id: str, batch_key: str):
    """Build a ``run_*`` function crawling one English finance batch."""

    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        from app.services.news.sources.en_fin_batch import (
            EnFinBatchCrawler,
        )

        async def _go():
            crawler = EnFinBatchCrawler(batch_key)
            return await crawler.fetch_recent()

        try:
            articles = _run_async(_go())
        except Exception as exc:
            logger.exception("en fin batch %s crawl failed: %s", batch_key, exc)
            return {
                "fetched": 0,
                "written": 0,
                "skipped": True,
                "skip_reason": f"crawl_error: {exc}",
            }

        if not articles:
            return {"fetched": 0, "written": 0, "skipped": True, "skip_reason": "no_articles"}

        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}

    _run.__name__ = f"run_en_fin_{batch_key}_crawl"
    return _run


for _job_id, _label, _batch in EN_FIN_BATCH_JOBS:
    globals()[f"run_en_fin_{_batch}_crawl"] = _enf_batch_job(_job_id, _batch)


# ── Official institution + industry vertical batches (added 2026-08-02) ──
#
# 56 live-verified feeds — central banks (Fed speeches/monetary, BIS,
# Riksbank, Dallas Fed), US regulators & official statistics (SEC,
# CFTC, Treasury, FDIC, FTC, White House, BEA, EIA, DOE, CBO), UK FCA,
# think tanks (CFR, Cato, Hoover, McKinsey) and industry verticals
# (Industry Dive family, medtech, tech, EV/auto, semiconductors,
# mining/shipping/aero/defense, real estate). Table and ECS
# verification evidence live in
# app/services/news/sources/official_batch.py. Same no-LLM rationale
# as the other batch waves.

from app.services.news.sources.official_batch import (  # noqa: E402
    OFFICIAL_BATCH_JOBS,
)


def _ofc_batch_job(job_id: str, batch_key: str):
    """Build a ``run_*`` function crawling one official/industry batch."""

    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        from app.services.news.sources.official_batch import (
            OfficialBatchCrawler,
        )

        async def _go():
            crawler = OfficialBatchCrawler(batch_key)
            return await crawler.fetch_recent()

        try:
            articles = _run_async(_go())
        except Exception as exc:
            logger.exception("official batch %s crawl failed: %s", batch_key, exc)
            return {
                "fetched": 0,
                "written": 0,
                "skipped": True,
                "skip_reason": f"crawl_error: {exc}",
            }

        if not articles:
            return {"fetched": 0, "written": 0, "skipped": True, "skip_reason": "no_articles"}

        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}

    _run.__name__ = f"run_official_{batch_key}_crawl"
    return _run


for _job_id, _label, _batch in OFFICIAL_BATCH_JOBS:
    globals()[f"run_official_{_batch}_crawl"] = _ofc_batch_job(_job_id, _batch)


# ── Chinese media / Asia / crypto increment batches (added 2026-08-02) ──
#
# 58 live-verified feeds — HK/TW Chinese media (RTHK, 星岛, 报导者,
# 关键评论网…), mainland weeklies, JP media & tech (NHK, 东洋经济,
# 朝日/每日/产经, ITmedia…), KR (韩联社, 京乡, Money Today), SEA
# English and 19 crypto outlets (EN/JA/KO). Table and ECS verification
# evidence live in app/services/news/sources/zh_media_batch.py. 14
# verified-but-colliding feeds were dropped (see module docstring).
# Same no-LLM rationale as the other batch waves.

from app.services.news.sources.zh_media_batch import (  # noqa: E402
    ZH_MEDIA_BATCH_JOBS,
)


def _zhm_batch_job(job_id: str, batch_key: str):
    """Build a ``run_*`` function crawling one zh-media batch."""

    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        from app.services.news.sources.zh_media_batch import (
            ZhMediaBatchCrawler,
        )

        async def _go():
            crawler = ZhMediaBatchCrawler(batch_key)
            return await crawler.fetch_recent()

        try:
            articles = _run_async(_go())
        except Exception as exc:
            logger.exception("zh media batch %s crawl failed: %s", batch_key, exc)
            return {
                "fetched": 0,
                "written": 0,
                "skipped": True,
                "skip_reason": f"crawl_error: {exc}",
            }

        if not articles:
            return {"fetched": 0, "written": 0, "skipped": True, "skip_reason": "no_articles"}

        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}

    _run.__name__ = f"run_zh_media_{batch_key}_crawl"
    return _run


for _job_id, _label, _batch in ZH_MEDIA_BATCH_JOBS:
    globals()[f"run_zh_media_{_batch}_crawl"] = _zhm_batch_job(_job_id, _batch)


# ── Investment education / explainer batches (added 2026-08-02) ──
#
# 17 curated knowledge feeds for the 学习中心 — EN blogs/Substacks
# (Humble Dollar, Klement, Macro Compass…), 10 YouTube education
# channels (Ben Felix, Damodaran, Patrick Boyle…) and 股感 StockFeel.
# Table and ECS verification evidence live in
# app/services/news/sources/edu_batch.py. Same no-LLM rationale as the
# other batch waves.

from app.services.news.sources.edu_batch import (  # noqa: E402
    EDU_BATCH_JOBS,
)


def _edu_batch_job(job_id: str, batch_key: str):
    """Build a ``run_*`` function crawling one education batch."""

    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        from app.services.news.sources.edu_batch import (
            EduBatchCrawler,
        )

        async def _go():
            crawler = EduBatchCrawler(batch_key)
            return await crawler.fetch_recent()

        try:
            articles = _run_async(_go())
        except Exception as exc:
            logger.exception("edu batch %s crawl failed: %s", batch_key, exc)
            return {
                "fetched": 0,
                "written": 0,
                "skipped": True,
                "skip_reason": f"crawl_error: {exc}",
            }

        if not articles:
            return {"fetched": 0, "written": 0, "skipped": True, "skip_reason": "no_articles"}

        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}

    _run.__name__ = f"run_edu_{batch_key}_crawl"
    return _run


for _job_id, _label, _batch in EDU_BATCH_JOBS:
    globals()[f"run_edu_{_batch}_crawl"] = _edu_batch_job(_job_id, _batch)


# ── New Chinese news sources (added 2026-07-18) ──

@_record_etl("news_wallstreetcn_5m")
def run_wallstreetcn_crawl() -> dict[str, int]:
    from app.services.news.sources.wallstreetcn import WallstreetcnCrawler

    async def _go():
        async with WallstreetcnCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("wallstreetcn crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


@_record_etl("news_36kr_10m")
def run_kr36_crawl() -> dict[str, int]:
    from app.services.news.sources.kr36 import Kr36Crawler

    async def _go():
        async with Kr36Crawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("36kr crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


@_record_etl("news_huxiu_10m")
def run_huxiu_crawl() -> dict[str, int]:
    from app.services.news.sources.huxiu import HuxiuCrawler

    async def _go():
        async with HuxiuCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception:
        # Re-raise so _record_etl marks the run "failed"; returning zeros
        # here recorded a fake success and hid source outages.
        logger.exception("huxiu crawl failed")
        raise


@_record_etl("news_jiemian_10m")
def run_jiemian_crawl() -> dict[str, int]:
    from app.services.news.sources.jiemian import JiemianCrawler

    async def _go():
        async with JiemianCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception:
        # Re-raise so _record_etl marks the run "failed"; returning zeros
        # here recorded a fake success and hid source outages.
        logger.exception("jiemian crawl failed")
        raise


@_record_etl("news_caixin_10m")
def run_caixin_crawl() -> dict[str, int]:
    from app.services.news.sources.caixin import CaixinCrawler

    async def _go():
        async with CaixinCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception:
        # Re-raise so _record_etl marks the run "failed"; returning zeros
        # here recorded a fake success and hid source outages.
        logger.exception("caixin crawl failed")
        raise


@_record_etl("news_chinanews_finance_15m")
def run_chinanews_finance_crawl() -> dict[str, int]:
    from app.services.news.sources.chinanews_finance import ChinanewsFinanceCrawler

    async def _go():
        async with ChinanewsFinanceCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("chinanews_finance crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


@_record_etl("news_stats_gov_30m")
def run_stats_gov_crawl() -> dict[str, int]:
    from app.services.news.sources.stats_gov import StatsGovCrawler

    async def _go():
        async with StatsGovCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception:
        # Re-raise so _record_etl marks the run "failed"; returning zeros
        # here recorded a fake success and hid source outages.
        logger.exception("stats_gov crawl failed")
        raise


# ── International & official sources (added 2026-07-21) ──

@_record_etl("news_cls_5m")
def run_cls_crawl() -> dict[str, int]:
    from app.services.news.sources.cls import ClsCrawler

    async def _go():
        async with ClsCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("cls crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


@_record_etl("news_marketwatch_10m")
def run_marketwatch_crawl() -> dict[str, int]:
    from app.services.news.sources.rss_simple import MarketWatchCrawler

    async def _go():
        async with MarketWatchCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("marketwatch crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


@_record_etl("news_zerohedge_15m")
def run_zerohedge_crawl() -> dict[str, int]:
    from app.services.news.sources.rss_simple import ZeroHedgeCrawler

    async def _go():
        async with ZeroHedgeCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
    except Exception as exc:
        logger.exception("zerohedge crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}

    # ZeroHedge is blog-style self-media — run the same marketing
    # filter as the WeChat job, with the English prompt variant.
    marketing_filter = _build_marketing_filter("zerohedge", english=True)
    filtered, rejected = _apply_marketing_filter(articles, marketing_filter)
    written = _write_to_db(filtered)
    return {
        "fetched": len(articles),
        "written": written,
        "rejected_marketing": rejected,
    }


@_record_etl("news_seekingalpha_10m")
def run_seekingalpha_crawl() -> dict[str, int]:
    from app.services.news.sources.rss_simple import SeekingAlphaCrawler

    async def _go():
        async with SeekingAlphaCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("seekingalpha crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


@_record_etl("news_ft_15m")
def run_ft_crawl() -> dict[str, int]:
    from app.services.news.sources.rss_simple import FtCrawler

    async def _go():
        async with FtCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("ft crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


@_record_etl("news_investing_15m")
def run_investing_crawl() -> dict[str, int]:
    from app.services.news.sources.rss_simple import InvestingCrawler

    async def _go():
        async with InvestingCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("investing crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


@_record_etl("news_decrypt_15m")
def run_decrypt_crawl() -> dict[str, int]:
    from app.services.news.sources.rss_simple import DecryptCrawler

    async def _go():
        async with DecryptCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
    except Exception as exc:
        logger.exception("decrypt crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}

    # Decrypt is blog-style crypto media — run the same marketing
    # filter as the WeChat job, with the English prompt variant.
    marketing_filter = _build_marketing_filter("decrypt", english=True)
    filtered, rejected = _apply_marketing_filter(articles, marketing_filter)
    written = _write_to_db(filtered)
    return {
        "fetched": len(articles),
        "written": written,
        "rejected_marketing": rejected,
    }


@_record_etl("news_federal_reserve_60m")
def run_federal_reserve_crawl() -> dict[str, int]:
    from app.services.news.sources.rss_simple import FederalReserveCrawler

    async def _go():
        async with FederalReserveCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("federal_reserve crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


@_record_etl("news_ecb_60m")
def run_ecb_crawl() -> dict[str, int]:
    from app.services.news.sources.rss_simple import EcbCrawler

    async def _go():
        async with EcbCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("ecb crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


@_record_etl("news_bankofengland_60m")
def run_bankofengland_crawl() -> dict[str, int]:
    from app.services.news.sources.rss_simple import BankOfEnglandCrawler

    async def _go():
        async with BankOfEnglandCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("bankofengland crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


@_record_etl("news_bbc_business_15m")
def run_bbc_business_crawl() -> dict[str, int]:
    from app.services.news.sources.rss_simple import BbcBusinessCrawler

    async def _go():
        async with BbcBusinessCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("bbc_business crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


@_record_etl("news_arxiv_qfin_360m")
def run_arxiv_qfin_crawl() -> dict[str, int]:
    from app.services.news.sources.rss_simple import ArxivQfinCrawler

    async def _go():
        async with ArxivQfinCrawler() as c:
            return await c.crawl()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("arxiv_qfin crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


# ── US ──

@_record_etl("news_yahoo_5m")
def run_yahoo_crawl() -> dict[str, int]:
    from app.services.news.sources.yahoo_rss import YahooFinanceCrawler

    async def _go():
        async with YahooFinanceCrawler() as c:
            return await c.fetch(_DEFAULT_US_TICKERS)

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("yahoo crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


@_record_etl("news_cnbc_5m")
def run_cnbc_crawl() -> dict[str, int]:
    from app.services.news.sources.cnbc import CNBCCrawler

    async def _go():
        async with CNBCCrawler() as c:
            return await c.fetch()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("cnbc crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


@_record_etl("news_sec_edgar_30m")
def run_sec_edgar_crawl() -> dict[str, int]:
    from datetime import datetime, timedelta

    from app.services.news.sources.sec_edgar import SecEdgarCrawler

    async def _go():
        async with SecEdgarCrawler() as c:
            since = datetime.now(UTC) - timedelta(days=7)
            return await c.fetch(_SEC_EDGAR_TICKER_TO_CIK, since=since)

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("sec_edgar crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


@_record_etl("news_reddit_5m")
def run_reddit_crawl() -> dict[str, int]:
    from app.services.news.sources.reddit import RedditCrawler

    # Skip BEFORE building an HTTP client — without credentials the
    # crawler cannot authenticate, so there's nothing useful to do
    # and the cron tick should be silent. The "skipped" result is
    # still recorded to ETLLog by :func:`_record_etl` so the health
    # endpoint can distinguish "configured but failing" from "not
    # configured".
    crawler = RedditCrawler()
    if not crawler.has_credentials:
        logger.info(
            "reddit crawler skipped: credentials not configured "
            "(set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET to enable)"
        )
        return {
            "fetched": 0,
            "written": 0,
            "skipped": True,
            "skip_reason": "missing_credentials",
        }

    async def _go():
        async with crawler as c:
            return await c.fetch_universe()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("reddit crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


# ── Crypto ──

@_record_etl("news_coindesk_5m")
def run_coindesk_crawl() -> dict[str, int]:
    from app.services.news.sources.coindesk import CoinDeskCrawler

    async def _go():
        async with CoinDeskCrawler() as c:
            return await c.fetch()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("coindesk crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


@_record_etl("news_cointelegraph_5m")
def run_cointelegraph_crawl() -> dict[str, int]:
    from app.services.news.sources.cointelegraph import CointelegraphCrawler

    async def _go():
        async with CointelegraphCrawler() as c:
            return await c.fetch()

    try:
        articles = _run_async(_go())
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}
    except Exception as exc:
        logger.exception("cointelegraph crawl failed: %s", exc)
        return {"fetched": 0, "written": 0}


# ── Independent blog / Substack sources (added 2026-07-27) ──

def _simple_rss_job(job_id: str, crawler_class_path: str) -> Callable[[], dict[str, int]]:
    """Build an ETL-logged crawl job for a :class:`SimpleRssCrawler` subclass.

    The 13 independent blog/Substack sources differ only in crawler
    class — generating the wrappers avoids 13 copies of the same
    fetch→persist→log skeleton. Failure semantics match the hand-written
    wrappers: log + return zeros, never crash the scheduler.
    """
    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        import importlib

        module_name, class_name = crawler_class_path.rsplit(".", 1)
        crawler_cls = getattr(importlib.import_module(module_name), class_name)

        async def _go():
            async with crawler_cls() as c:
                return await c.crawl()

        try:
            articles = _run_async(_go())
            written = _write_to_db(articles)
            return {"fetched": len(articles), "written": written}
        except Exception as exc:
            logger.exception("%s crawl failed: %s", job_id, exc)
            return {"fetched": 0, "written": 0}

    return _run


_RSS_SIMPLE = "app.services.news.sources.rss_simple"

# (job_id, display name for the health panel, interval minutes, crawler class)
INDEPENDENT_RSS_JOBS: list[tuple[str, str, int, str]] = [
    ("news_wolfstreet_30m", "Wolf Street 博客", 30, f"{_RSS_SIMPLE}.WolfStreetCrawler"),
    ("news_calculatedrisk_30m", "Calculated Risk 宏观博客", 30, f"{_RSS_SIMPLE}.CalculatedRiskCrawler"),
    ("news_awealthofcommonsense_30m", "A Wealth of Common Sense", 30, f"{_RSS_SIMPLE}.WealthCommonSenseCrawler"),
    ("news_ofdollarsanddata_30m", "Of Dollars and Data", 30, f"{_RSS_SIMPLE}.OfDollarsAndDataCrawler"),
    ("news_marginalrevolution_30m", "Marginal Revolution", 30, f"{_RSS_SIMPLE}.MarginalRevolutionCrawler"),
    ("news_ritholtz_30m", "The Big Picture (Ritholtz)", 30, f"{_RSS_SIMPLE}.RitholtzCrawler"),
    ("news_netinterest_60m", "Net Interest 金融深度", 60, f"{_RSS_SIMPLE}.NetInterestCrawler"),
    ("news_doomberg_60m", "Doomberg 产业能源", 60, f"{_RSS_SIMPLE}.DoombergCrawler"),
    ("news_apricitas_60m", "Apricitas Economics", 60, f"{_RSS_SIMPLE}.ApricitasCrawler"),
    ("news_noahpinion_60m", "Noahpinion", 60, f"{_RSS_SIMPLE}.NoahpinionCrawler"),
    ("news_econbrowser_60m", "Econbrowser 学术宏观", 60, f"{_RSS_SIMPLE}.EconbrowserCrawler"),
    ("news_theovershoot_60m", "The Overshoot 宏观研究", 60, f"{_RSS_SIMPLE}.TheOvershootCrawler"),
    ("news_quantpedia_120m", "Quantpedia 量化研究", 120, f"{_RSS_SIMPLE}.QuantpediaCrawler"),
    # WeChat OA via the public wechat2rss mirror (no wewe-rss login
    # required). Full body arrives in content:encoded. 60m cadence —
    # these accounts post at most a few times a day.
    ("news_wechat_maobidao_60m", "猫笔刀 (公众号镜像)", 60, f"{_RSS_SIMPLE}.WechatMaobidaoCrawler"),
    ("news_wechat_sixianggangyin_60m", "思想钢印 (公众号镜像)", 60, f"{_RSS_SIMPLE}.WechatSixianggangyinCrawler"),
]

# Materialise one module-level job function per entry so APScheduler can
# import them by name (and so ``dir()`` shows them for tests).
for _job_id, _label, _minutes, _path in INDEPENDENT_RSS_JOBS:
    globals()[f"run_{_job_id.removeprefix('news_').rsplit('_', 1)[0]}_crawl"] = _simple_rss_job(_job_id, _path)


# ── Translation drain (added 2026-07-26) ──

@_record_etl("news_translate_10m")
def run_translate_pending_job() -> dict[str, int]:
    """Drain non-Chinese articles that still lack a Chinese translation.

    Covers both the rows the ingest-time pass skipped (time budget) and
    the historical backfill, newest first. Fully fail-safe — an LLM
    outage records a failed run instead of crashing the scheduler.
    """
    from app.services.news.scheduler_translate_news import run_translate_pending

    try:
        return run_translate_pending()
    except Exception as exc:
        logger.exception("translate pending failed: %s", exc)
        return {"fetched": 0, "written": 0}


# ── AI summary drain (added 2026-07-29, 方向 D) ──

@_record_etl("news_summarize_10m")
def run_summarize_pending_job() -> dict[str, int]:
    """Drain ≥3-importance articles that still lack a Chinese AI summary.

    Fully fail-safe — an LLM outage records a skipped/failed run instead
    of crashing the scheduler; untouched rows retry on the next tick.
    """
    from app.services.news.scheduler_summarize_news import run_summarize_pending

    try:
        return run_summarize_pending()
    except Exception as exc:
        logger.exception("summarize pending failed: %s", exc)
        return {"fetched": 0, "written": 0}


# ── Macro (FRED) ──

@record_etl("fred_macro_daily", source="fred")
def run_fred_refresh(lookback_days: int = 180) -> dict[str, Any]:
    """Pull the latest ~N days for every registered FRED series.

    Called from APScheduler on weekdays after FRED publishes the bulk
    of its daily data (~15:00 ET).  Safe to re-run; the upsert is
    idempotent.
    """
    from app.core.database import SessionLocal
    from app.services.macro.fred_service import FredService

    db = SessionLocal()
    try:
        service = FredService(db=db)
        result = service.refresh(lookback_days=lookback_days)
        return {
            "written": result.get("written", 0),
            "series_count": result.get("series_count", 0),
            "failed": len(result.get("failed", [])),
        }
    except Exception as exc:
        logger.exception("FRED refresh failed: %s", exc)
        return {"written": 0, "series_count": 0, "failed": -1}
    finally:
        db.close()


# ── AI 产业链批次（added 2026-08-04）──
#
# 中美 AI 全产业链资讯扩容：中文 37 feeds（ai_cn_batch，a-d 四批）
# + 英文 99 feeds（ai_us_batch，a-j 十批）。候选来自五路搜罗报告
# （docs/dev-notes/ai-chain-sources/20260804-*.md），全部实测通过
# 且与存量 1012 源零重叠（模块内测试断言）。market 规则同
# en_fin_batch：中文=cn_a、英文=us，绝不写 global（_GLOBAL_MARKETS
# 白名单只有 cn_a/us/crypto）。

from app.services.news.sources.ai_cn_batch import (  # noqa: E402
    AI_CN_BATCH_JOBS,
)
from app.services.news.sources.ai_us_batch import (  # noqa: E402
    AI_US_BATCH_JOBS,
)


def _aicn_batch_job(job_id: str, batch_key: str):
    """Build a ``run_*`` function crawling one AI-chain CN batch."""

    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        from app.services.news.sources.ai_cn_batch import (
            AiCnBatchCrawler,
        )

        async def _go():
            crawler = AiCnBatchCrawler(batch_key)
            return await crawler.fetch_recent()

        try:
            articles = _run_async(_go())
        except Exception as exc:
            logger.exception("ai cn batch %s crawl failed: %s", batch_key, exc)
            return {
                "fetched": 0,
                "written": 0,
                "skipped": True,
                "skip_reason": f"crawl_error: {exc}",
            }

        if not articles:
            return {"fetched": 0, "written": 0, "skipped": True, "skip_reason": "no_articles"}

        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}

    _run.__name__ = f"run_ai_cn_{batch_key}_crawl"
    return _run


for _job_id, _label, _batch in AI_CN_BATCH_JOBS:
    globals()[f"run_ai_cn_{_batch}_crawl"] = _aicn_batch_job(_job_id, _batch)


def _aius_batch_job(job_id: str, batch_key: str):
    """Build a ``run_*`` function crawling one AI-chain US batch."""

    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        from app.services.news.sources.ai_us_batch import (
            AiUsBatchCrawler,
        )

        async def _go():
            crawler = AiUsBatchCrawler(batch_key)
            return await crawler.fetch_recent()

        try:
            articles = _run_async(_go())
        except Exception as exc:
            logger.exception("ai us batch %s crawl failed: %s", batch_key, exc)
            return {
                "fetched": 0,
                "written": 0,
                "skipped": True,
                "skip_reason": f"crawl_error: {exc}",
            }

        if not articles:
            return {"fetched": 0, "written": 0, "skipped": True, "skip_reason": "no_articles"}

        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}

    _run.__name__ = f"run_ai_us_{batch_key}_crawl"
    return _run


for _job_id, _label, _batch in AI_US_BATCH_JOBS:
    globals()[f"run_ai_us_{_batch}_crawl"] = _aius_batch_job(_job_id, _batch)
