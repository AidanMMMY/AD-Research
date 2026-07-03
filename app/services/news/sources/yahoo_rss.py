"""Yahoo Finance RSS crawler.

Public RSS endpoint, no API key required. Returns headlines for one or
more tickers, suitable for daily news / sentiment analysis.

Endpoint
--------
``https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US``

Rate limit
----------
We self-impose 30 requests/minute to be polite. Yahoo's actual limit
is undocumented but well above that for non-abusive usage. As of mid
2026 Yahoo is returning HTTP 429 to non-browser UAs from server
infrastructure, so a 429 / 403 response is treated as a fallback
trigger: see :meth:`YahooFinanceCrawler._fetch_with_fallback`.

Symbols
-------
``fetch()`` accepts either a single ticker (``"AAPL"``) or a list
(``["AAPL", "TSLA"]``). The crawler's main job is per-ticker headlines;
it returns a list of :class:`RawArticle`. Each article's ``extra``
dict contains the originating ticker so downstream storage can write
the ``news_article_symbol`` link.
"""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

import httpx

from app.config import get_settings
from app.services.news.crawler.rate_limiter import AsyncTokenBucket
from app.services.news.crawler.symbol_extractor import extract_symbols
from app.services.news.crawler.types import RawArticle

logger = logging.getLogger(__name__)

YAHOO_RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline"

# Status codes that signal Yahoo is rejecting our non-browser UA / IP
# and that we should fall back to Finnhub company-news instead.
_FALLBACK_STATUS_CODES = frozenset({429, 403})

# How far back to ask Finnhub for when we fall back. Finnhub's free
# company-news endpoint returns at most one week of headlines per call.
_FALLBACK_LOOKBACK_DAYS = 7

# Article ``source`` value used for items produced by the Finnhub
# fallback. We intentionally tag these rows with the same value as
# the primary Yahoo path (``"yahoo_finance"``) so the news-health
# aggregator (which counts per ``source``) can sum both streams
# together. The fallback provenance is preserved in
# ``extra["fallback_from"]`` so consumers that care about the
# distinction can still tell primary vs fallback apart.
_FALLBACK_SOURCE_NAME = "yahoo_finance"


def _to_internal(ticker: str) -> str:
    return f"{ticker.upper().strip()}.US"


class YahooFinanceCrawler:
    """Crawl Yahoo Finance per-ticker headline RSS feeds.

    On HTTP 429 / 403 (Yahoo rejecting non-browser traffic) this
    crawler transparently falls back to Finnhub's
    ``/company-news`` endpoint, provided ``FINNHUB_API_KEY`` is set
    in the environment / settings. If no key is configured the
    fallback is silently skipped and the failing ticker returns no
    articles (matching the existing warning + continue behavior).
    """

    source_name = "yahoo_finance"
    rate_limit_per_min = 30
    timeout_seconds = 15.0

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        rate_limiter: AsyncTokenBucket | None = None,
        finnhub_provider: Any | None = None,
    ) -> None:
        self._client = client
        self._owns_client = client is None
        self._limiter = rate_limiter or AsyncTokenBucket(self.rate_limit_per_min)
        # Allow tests / callers to inject a mock provider. Lazy-built
        # from settings on first fallback attempt.
        self._finnhub_provider_override = finnhub_provider

    async def __aenter__(self) -> "YahooFinanceCrawler":
        if self._client is None:
            self._client = await self._build_client()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _build_client(self) -> httpx.AsyncClient:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.5 Safari/605.1.15"
            ),
            "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
        }
        return httpx.AsyncClient(
            headers=headers,
            timeout=self.timeout_seconds,
            follow_redirects=True,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch(self, tickers: str | Iterable[str]) -> list[RawArticle]:
        """Fetch headlines for one or more tickers.

        Returns a list of :class:`RawArticle`. The ``extra`` dict on
        each article carries ``{"ticker": "AAPL"}`` for traceability.
        On a 429 / 403 the per-ticker fetch transparently falls back
        to Finnhub's company-news endpoint.
        """
        if isinstance(tickers, str):
            ticker_list = [tickers]
        else:
            ticker_list = [t for t in tickers if t]
        if not ticker_list:
            return []

        articles: list[RawArticle] = []
        async with self:
            for ticker in ticker_list:
                try:
                    arts = await self._fetch_with_fallback(ticker)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Yahoo RSS failed for %s: %s", ticker, exc)
                    continue
                articles.extend(arts)
        return articles

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _fetch_with_fallback(self, ticker: str) -> list[RawArticle]:
        """Fetch one ticker, falling back to Finnhub on 429 / 403."""
        try:
            return await self._fetch_one(ticker)
        except httpx.HTTPStatusError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status not in _FALLBACK_STATUS_CODES:
                raise
            return await self._fetch_finnhub_fallback(ticker, status=status)
        except httpx.RequestError as exc:
            # Connection reset / DNS / TLS — also treat as transient
            # enough to try the fallback. (Yahoo intermittently throws
            # these when their edge redirects aggressively.)
            logger.info(
                "Yahoo RSS transport error for %s (%s); trying Finnhub fallback",
                ticker,
                exc,
            )
            return await self._fetch_finnhub_fallback(ticker, status=None)

    async def _fetch_finnhub_fallback(
        self, ticker: str, *, status: int | None
    ) -> list[RawArticle]:
        """Fetch ``ticker`` news from Finnhub as a fallback.

        Returns an empty list (with a warning log) when no API key is
        configured, so the caller can keep going without raising.
        """
        if not self._finnhub_key_available():
            logger.warning(
                "Yahoo RSS returned HTTP %s for %s and FINNHUB_API_KEY is "
                "not set — no fallback available.",
                status if status is not None else "transport-error",
                ticker,
            )
            return []

        provider = self._get_finnhub_provider()
        to_date = date.today()
        from_date = to_date - timedelta(days=_FALLBACK_LOOKBACK_DAYS)
        try:
            # ``fetch_company_news`` is a blocking HTTP call (uses
            # ``requests``); push it to a worker thread so we don't
            # stall the event loop for the rest of the crawl batch.
            news = await asyncio.to_thread(
                provider.fetch_company_news,
                ticker,
                from_date,
                to_date,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Finnhub fallback failed for %s: %s", ticker, exc
            )
            return []

        articles = [_finnhub_item_to_article(item, ticker) for item in news]
        articles = [a for a in articles if a is not None]
        if articles:
            logger.info(
                "Yahoo RSS fallback to Finnhub succeeded for %s "
                "(status=%s, articles=%d)",
                ticker,
                status if status is not None else "transport-error",
                len(articles),
            )
        return articles

    def _finnhub_key_available(self) -> bool:
        try:
            return bool(get_settings().finnhub_api_key)
        except Exception:  # pragma: no cover - defensive
            return False

    def _get_finnhub_provider(self) -> Any:
        if self._finnhub_provider_override is not None:
            return self._finnhub_provider_override
        from app.data.providers.finnhub_provider import FinnhubProvider

        return FinnhubProvider()

    async def _fetch_one(self, ticker: str) -> list[RawArticle]:
        await self._limiter.acquire()
        assert self._client is not None
        url = YAHOO_RSS_URL
        params = {"s": ticker, "region": "US", "lang": "en-US"}
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        return self._parse_xml(resp.text, ticker)

    def _parse_xml(self, xml_text: str, ticker: str) -> list[RawArticle]:
        """Parse an RSS-2.0 XML document into ``RawArticle`` objects."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            logger.warning("Yahoo RSS XML parse error for %s: %s", ticker, exc)
            return []

        channel = root.find("channel")
        if channel is None:
            return []

        out: list[RawArticle] = []
        for item in channel.findall("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or link).strip()
            pub = (item.findtext("pubDate") or "").strip()
            description = (item.findtext("description") or "").strip()
            author = (item.findtext("author") or item.findtext("dc:creator") or "").strip()
            if not title or not link:
                continue
            published_at = _parse_rfc822_date(pub) or datetime.now(tz=timezone.utc)

            art = RawArticle(
                source=self.source_name,
                source_id=guid or link,
                url=link,
                title=title,
                published_at=published_at,
                body=description or None,
                body_html=description or None,
                author=author or None,
                language="en",
                market="us",
                extra={"ticker": ticker.upper()},
            )
            # Auto-populate symbols from title+body.
            symbols = extract_symbols(f"{title}\n{description}", url=link)
            if ticker:
                symbols.add(_to_internal(ticker))
            art.engagement = {"symbols_extracted": sorted(symbols)}
            out.append(art)
        return out


def _finnhub_item_to_article(
    item: dict[str, Any], ticker: str
) -> RawArticle | None:
    """Convert a Finnhub company-news dict into a :class:`RawArticle`.

    Returns ``None`` if the item is missing the required fields.
    """
    headline = (item.get("headline") or "").strip()
    url = (item.get("url") or "").strip()
    if not headline or not url:
        return None

    ts = item.get("datetime")
    if isinstance(ts, (int, float)):
        published_at = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    elif isinstance(ts, str) and ts:
        try:
            published_at = datetime.fromisoformat(ts)
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=timezone.utc)
        except ValueError:
            published_at = datetime.now(tz=timezone.utc)
    else:
        published_at = datetime.now(tz=timezone.utc)

    summary = (item.get("summary") or "").strip()
    source_name = (item.get("source") or "").strip() or None
    category = (item.get("category") or "").strip() or None

    art = RawArticle(
        source=_FALLBACK_SOURCE_NAME,
        source_id=url,
        url=url,
        title=headline,
        published_at=published_at,
        body=summary or None,
        body_html=summary or None,
        author=source_name,
        language="en",
        market="us",
        extra={
            "ticker": ticker.upper(),
            "fallback_from": "yahoo_finance",
            "finnhub_category": category,
            "finnhub_source": source_name,
        },
    )
    symbols = extract_symbols(f"{headline}\n{summary}", url=url)
    if ticker:
        symbols.add(_to_internal(ticker))
    art.engagement = {"symbols_extracted": sorted(symbols)}
    return art


def _parse_rfc822_date(value: str) -> datetime | None:
    """Parse an RFC-822 / RFC-2822 date string (Yahoo format).

    Returns ``None`` on failure rather than raising. Always returns
    a UTC-aware datetime.
    """
    if not value:
        return None
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(value)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None
