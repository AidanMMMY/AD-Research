"""Yahoo Finance RSS crawler.

Public RSS endpoint, no API key required. Returns headlines for one or
more tickers, suitable for daily news / sentiment analysis.

Endpoint
--------
``https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US``

Rate limit
----------
We self-impose 30 requests/minute to be polite. Yahoo's actual limit
is undocumented but well above that for non-abusive usage.

Symbols
-------
``fetch()`` accepts either a single ticker (``"AAPL"``) or a list
(``["AAPL", "TSLA"]``). The crawler's main job is per-ticker headlines;
it returns a list of :class:`RawArticle`. Each article's ``extra``
dict contains the originating ticker so downstream storage can write
the ``news_article_symbol`` link.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Iterable

import httpx

from app.services.news.crawler.rate_limiter import AsyncTokenBucket
from app.services.news.crawler.symbol_extractor import extract_symbols
from app.services.news.crawler.types import RawArticle

logger = logging.getLogger(__name__)

YAHOO_RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline"


def _to_internal(ticker: str) -> str:
    return f"{ticker.upper().strip()}.US"


class YahooFinanceCrawler:
    """Crawl Yahoo Finance per-ticker headline RSS feeds."""

    source_name = "yahoo_finance"
    rate_limit_per_min = 30
    timeout_seconds = 15.0

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        rate_limiter: AsyncTokenBucket | None = None,
    ) -> None:
        self._client = client
        self._owns_client = client is None
        self._limiter = rate_limiter or AsyncTokenBucket(self.rate_limit_per_min)

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
                    arts = await self._fetch_one(ticker)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Yahoo RSS failed for %s: %s", ticker, exc)
                    continue
                articles.extend(arts)
        return articles

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

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
