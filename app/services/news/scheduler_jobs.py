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
import logging
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable

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
                    start_time=datetime.now(timezone.utc),
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
                        log_row.end_time = datetime.now(timezone.utc)
                        log_row.records_count = 0
                        log_row.error_msg = str(exc)[:1000]
                        db.commit()
                except Exception:  # pragma: no cover - defensive
                    try:
                        db.rollback()
                    except Exception:
                        pass
                finally:
                    db.close()
                raise

            # Successful return path.
            try:
                if log_row is not None:
                    log_row.status = "success"
                    log_row.end_time = datetime.now(timezone.utc)
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
                try:
                    db.rollback()
                except Exception:
                    pass
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
    return written


# ── A-share ──

def run_xinhua_crawl() -> dict[str, int]:
    # NOTE: xinhua RSS endpoints are currently 404; the cron job in
    # ``app.core.scheduler`` is disabled. The function is preserved
    # so callers that wire it explicitly still work, but we skip the
    # @_record_etl decorator since there is no scheduler job id.
    from app.services.news.sources.xinhua import XinhuaCrawler
    from app.services.news.normalizer import NewsNormalizer
    from app.core.database import SessionLocal

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

@_record_etl("news_wechat_zeping_15m")
def run_wechat_zeping_crawl() -> dict[str, int]:
    """Poll wewe-rss for the configured WeChat accounts.

    Always silent when wewe-rss is unreachable (returns
    ``fetched=0, written=0``); the ``_record_etl`` wrapper still
    records the run so the health page shows the failure mode. The
    marketing filter runs synchronously inside this tick — it caches
    DeepSeek verdicts for 24h so a 15-minute poll doesn't repeatedly
    bill the LLM for the same posts.
    """
    from app.services.news.sources.wechat_zeping import WechatZepingCrawler
    from app.services.news.filters.wechat_marketing_filter import WechatMarketingFilter

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

    filtered: list = []
    rejected = 0
    for art in articles:
        if marketing_filter is None:
            filtered.append(art)
            continue
        verdict = marketing_filter.classify(art.title, art.body)
        if verdict.is_knowledge:
            # Stash the verdict in extra for downstream debugging /
            # health-page telemetry.
            art.extra = dict(art.extra or {})
            art.extra["marketing_verdict"] = verdict.reason
            art.extra["marketing_confidence"] = verdict.confidence
            filtered.append(art)
        else:
            rejected += 1

    written = _write_to_db(filtered)
    return {
        "fetched": len(articles),
        "written": written,
        "rejected_marketing": rejected,
    }


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
    from datetime import datetime, timedelta, timezone
    from app.services.news.sources.sec_edgar import SecEdgarCrawler

    async def _go():
        async with SecEdgarCrawler() as c:
            since = datetime.now(timezone.utc) - timedelta(days=7)
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
