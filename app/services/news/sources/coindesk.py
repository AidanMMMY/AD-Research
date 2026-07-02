"""CoinDesk RSS crawler.

Pulls the public CoinDesk outbound RSS feed. No authentication required.

Endpoint
--------
``https://www.coindesk.com/arc/outboundfeeds/rss/``

The feed is the standard CoinDesk editorial RSS — top crypto news,
markets, policy. Each ``<item>`` includes ``<title>``, ``<link>``,
``<pubDate>``, ``<description>`` (HTML), and ``<dc:creator>`` /
``<author>`` for the reporter byline.

Rate limit
----------
We self-impose 20 requests/minute. CoinDesk's public endpoint is
generous to non-abusive clients; 20/min keeps us well clear of any
practical threshold while still being polite.

Symbols
-------
``fetch()`` accepts no arguments and returns the top items as a flat
list of :class:`RawArticle`. CoinDesk articles rarely use cashtags,
but the symbol extractor will still tag BTC/ETH/etc. when present.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from app.services.news.crawler.rate_limiter import AsyncTokenBucket
from app.services.news.crawler.symbol_extractor import extract_symbols
from app.services.news.crawler.types import RawArticle

logger = logging.getLogger(__name__)

COINDESK_RSS_URL = "https://www.coindesk.com/arc/outboundfeeds/rss/"


class CoinDeskCrawler:
    """Crawl CoinDesk top-news RSS feed (crypto market)."""

    source_name = "coindesk"
    rate_limit_per_min = 20
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

    async def __aenter__(self) -> "CoinDeskCrawler":
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

    async def fetch(self) -> list[RawArticle]:
        """Fetch CoinDesk top news."""
        async with self:
            await self._limiter.acquire()
            assert self._client is not None
            resp = await self._client.get(COINDESK_RSS_URL)
            resp.raise_for_status()
            return self._parse_xml(resp.text)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _parse_xml(self, xml_text: str) -> list[RawArticle]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            logger.warning("CoinDesk RSS XML parse error: %s", exc)
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
            author_el = item.find("author")
            if author_el is None or not (author_el.text or "").strip():
                # Try the namespaced dc:creator element.
                author_el = item.find("{http://purl.org/dc/elements/1.1/}creator")
            author = (author_el.text or "").strip() if author_el is not None else ""
            category = (item.findtext("category") or "").strip()

            if not title or not link:
                continue

            published_at = _parse_pub_date(pub) or datetime.now(tz=timezone.utc)
            plain_summary = _strip_html(description) or None
            art = RawArticle(
                source=self.source_name,
                source_id=guid or link,
                url=link,
                title=title,
                published_at=published_at,
                body=plain_summary,
                body_html=description or None,
                author=author or None,
                language="en",
                market="crypto",
                extra={"feed": "top_news", "category": category or "crypto_news"},
            )
            symbols = extract_symbols(f"{title}\n{description}", url=link)
            art.engagement = {"symbols_extracted": sorted(symbols)}
            out.append(art)
        return out


def _parse_pub_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Cheap HTML tag stripper — sufficient for RSS descriptions."""
    if not text:
        return ""
    no_tags = _HTML_TAG_RE.sub(" ", text)
    no_tags = (
        no_tags.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
    )
    return re.sub(r"\s+", " ", no_tags).strip()