"""Generic RSS/Atom parsing helpers shared by multiple news sources.

Provides a source-agnostic way to turn an RSS/Atom XML string into a list of
:class:`RawArticle`. The parser is intentionally conservative: it handles
common field names and date formats, drops items that are missing required
fields, and never raises — malformed items are skipped with a warning.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable

from app.services.news.crawler.types import RawArticle

logger = logging.getLogger(__name__)


_RSS_NAMESPACES = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "atom": "http://www.w3.org/2005/Atom",
}


def _find_text(parent: ET.Element, *paths: str) -> str | None:
    """Try several child tag paths and return the first non-empty text."""
    for path in paths:
        el = parent.find(path)
        if el is not None and el.text:
            return el.text.strip()
    return None


def _parse_date(value: str | None) -> datetime | None:
    """Best-effort date parsing for RSS/Atom timestamps."""
    if not value:
        return None
    value = value.strip()
    # RFC 2822 / RSS pubDate (e.g. "Sat, 18 Jul 2026 17:30:23 +0800")
    try:
        dt = parsedate_to_datetime(value)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        pass
    # ISO 8601 variants (e.g. "2026-07-18T17:30:23+08:00")
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    # 36kr style: "2026-07-18 17:30:23  +0800" (two spaces before tz)
    try:
        dt = datetime.strptime(value.replace("  +", " +"), "%Y-%m-%d %H:%M:%S %z")
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass
    return None


def _strip_html(text: str | None) -> str | None:
    """Drop HTML tags and collapse whitespace."""
    if not text:
        return None
    import re

    no_tags = re.sub(r"<[^>]+>", " ", text)
    no_tags = (
        no_tags.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
    )
    collapsed = re.sub(r"\s+", " ", no_tags).strip()
    return collapsed or None


def _extract_link(item: ET.Element) -> str | None:
    """Return the canonical URL for an RSS/Atom item."""
    link = _find_text(item, "link", f"{{{_RSS_NAMESPACES['atom']}}}link")
    if link:
        return link
    # Atom "link" element has href attribute.
    atom_link = item.find(f"{{{_RSS_NAMESPACES['atom']}}}link")
    if atom_link is not None:
        href = atom_link.get("href")
        if href:
            return href.strip()
    return None


def _extract_guid(item: ET.Element) -> str | None:
    """Return a stable ID for the item, falling back to the link."""
    guid = _find_text(item, "guid", f"{{{_RSS_NAMESPACES['atom']}}}id")
    if guid:
        return guid
    id_el = item.find("id")
    if id_el is not None and id_el.text:
        return id_el.text.strip()
    return _extract_link(item)


def _extract_pub_date(item: ET.Element, *, default_tz: timezone = timezone.utc) -> datetime | None:
    """Extract and normalize the item's publication timestamp."""
    value = _find_text(
        item,
        "pubDate",
        "pubTime",
        f"{{{_RSS_NAMESPACES['dc']}}}date",
        f"{{{_RSS_NAMESPACES['atom']}}}published",
        "published",
    )
    dt = _parse_date(value)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=default_tz)
    return dt.astimezone(timezone.utc)


def parse_rss_items(
    xml_text: str,
    *,
    source: str,
    market: str = "cn_a",
    language: str = "zh",
    default_author: str | None = None,
    max_items: int | None = None,
    default_tz: timezone = timezone.utc,
) -> list[RawArticle]:
    """Parse an RSS/Atom feed and return a list of :class:`RawArticle`.

    Args:
        xml_text: The raw XML body of the feed.
        source: The ``source`` identifier for every produced article.
        market: Market bucket (``cn_a``/``us``/etc.).
        language: Article language.
        default_author: Author name when the feed does not supply one.
        max_items: If set, only parse the first ``max_items`` items.
        default_tz: Timezone for naive timestamps (defaults to UTC).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("%s RSS parse error: %s", source, exc)
        return []

    channel = root.find("channel")
    if channel is not None:
        items = channel.findall("item")
    else:
        # Atom fallback
        items = root.findall(f"{{{_RSS_NAMESPACES['atom']}}}entry")
        if not items:
            items = root.findall("entry")

    out: list[RawArticle] = []
    for item in items[:max_items] if max_items else items:
        title = _find_text(item, "title")
        link = _extract_link(item)
        guid = _extract_guid(item)
        if not title or not link:
            logger.debug("%s RSS item skipped: missing title or link", source)
            continue

        description = _find_text(item, "description", "summary")
        body_html = description
        # Prefer full content:encoded if present.
        content_encoded = item.find(f"{{{_RSS_NAMESPACES['content']}}}encoded")
        if content_encoded is not None and content_encoded.text:
            body_html = content_encoded.text.strip()

        body = _strip_html(body_html)
        author = (
            _find_text(item, "author", f"{{{_RSS_NAMESPACES['dc']}}}creator")
            or default_author
        )
        published_at = _extract_pub_date(item, default_tz=default_tz) or datetime.now(
            tz=timezone.utc
        )

        category = _find_text(item, "category", f"{{{_RSS_NAMESPACES['dc']}}}subject")

        out.append(
            RawArticle(
                source=source,
                source_id=guid or link,
                url=link,
                title=title,
                body=body,
                body_html=body_html,
                author=author,
                published_at=published_at,
                language=language,
                market=market,
                extra={"category": category} if category else {},
            )
        )
    return out
