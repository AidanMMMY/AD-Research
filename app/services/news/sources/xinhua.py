"""Xinhua Finance RSS crawler.

Public RSS endpoint — no API key required. Xinhua is one of the two
state-owned news agencies in China so the headlines are typically
official macro / policy / earnings news.

Endpoint
--------
``http://www.news.cn/finance/rss.xml``  (a.k.a. www.xinhuanet.com)

Rate limit
----------
We self-impose 60 requests/minute via :attr:`rate_limit_per_min`.
Xinhua's public RSS feed is geared for news-aggregator use and
tolerates this rate comfortably.

Coverage
--------
Finance / 财经 channel — macro policy, central bank, regulator
announcements, listed-company news republished from Xinhua wire.

The endpoint is XML but not strict RSS-2.0 (lives in ``<rss>`` with
``<channel>``/``<item>``), so we parse it with a forgiving
:class:`xml.etree.ElementTree` walker rather than enforcing namespaces.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from app.services.news.crawler.base import BaseCrawler, _Response
from app.services.news.crawler.types import RawArticle

logger = logging.getLogger(__name__)

# Xinhua occasionally migrates the URL between xinhuanet.com and news.cn.
# We try the canonical news.cn one first and fall back to the legacy host
# on connection failure.
XINHUA_RSS_URLS: tuple[str, ...] = (
    "http://www.news.cn/finance/rss.xml",
    "http://www.xinhuanet.com/finance/rss.xml",
)


class XinhuaCrawler(BaseCrawler):
    """Crawl Xinhua Finance RSS feed.

    Usage::

        async with XinhuaCrawler() as crawler:
            raw = await crawler.crawl()  # one URL at a time

        # Or run as a one-shot scheduler job (commits to DB):
        inserted = await crawler.run(db)
    """

    source_name = "xinhua_rss"
    rate_limit_per_min = 60
    market = "cn_a"
    language = "zh"

    def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        kwargs.setdefault("rate_limit_per_min", self.rate_limit_per_min)
        super().__init__(**kwargs)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def crawl(self) -> list[RawArticle]:
        """Fetch and parse the Xinhua Finance RSS feed.

        Tries every URL in :data:`XINHUA_RSS_URLS`; only the last
        exception is re-raised (after all URLs have been exhausted).
        The base class rate-limits and handles retries.
        """
        last_exc: Exception | None = None
        for url in XINHUA_RSS_URLS:
            try:
                return await super().crawl(url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Xinhua RSS fetch failed for %s: %s", url, exc)
                last_exc = exc
                continue
        if last_exc is not None:
            raise last_exc
        return []

    async def parse(self, response: _Response) -> list[RawArticle]:
        """Parse an Xinhua RSS XML document into :class:`RawArticle`."""
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError as exc:
            logger.warning("Xinhua RSS XML parse error: %s", exc)
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
            published_at = _parse_pub_date(pub) or datetime.now(tz=timezone.utc)
            # Strip any HTML tags Xinhua sometimes leaves inside <description>.
            summary = _strip_html(description) if description else None

            art = RawArticle(
                source=self.source_name,
                source_id=guid or link,
                url=link,
                title=title,
                published_at=published_at,
                body=summary,
                body_html=description or None,
                author=author or None,
                language=self.language,
                market=self.market,
            )
            out.append(art)
        return out

    async def run(self, db) -> int:
        """Fetch, normalize, and persist. Returns inserted row count."""
        from app.services.news.normalizer import NewsNormalizer

        raw_articles = await self.crawl()
        if not raw_articles:
            return 0
        normalizer = NewsNormalizer(db)
        inserted = 0
        for raw in raw_articles:
            try:
                article = normalizer.normalize(raw)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Xinhua normalize failed: %s", exc)
                continue
            if article is not None:
                inserted += 1
        db.commit()
        return inserted


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_ENTITY_RE = re.compile(r"&(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);")


def _strip_html(value: str) -> str:
    """Strip HTML tags and decode common entities from a snippet."""
    if not value:
        return ""
    text = _HTML_TAG_RE.sub("", value)
    text = _HTML_ENTITY_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_pub_date(value: str) -> datetime | None:
    """Parse an RFC-822 / RFC-2822 date (Xinhua pubDate format).

    Returns ``None`` on failure rather than raising. Always returns
    a UTC-aware datetime.
    """
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
