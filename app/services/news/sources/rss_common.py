"""Generic RSS/Atom parsing helpers shared by multiple news sources.

Provides a source-agnostic way to turn an RSS/Atom XML string into a list of
:class:`RawArticle`. The parser is intentionally conservative: it handles
common field names and date formats, drops items that are missing required
fields, and never raises — malformed items are skipped with a warning.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timezone, tzinfo
from email.utils import parsedate_to_datetime

from app.services.news.crawler.types import RawArticle

logger = logging.getLogger(__name__)

# XML 1.0 forbids most C0 control characters; some feeds (cache plugins,
# hand-rolled templates) leak them and break strict parsing.
_ILLEGAL_XML_CHARS_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")
# `<!--comment--->` (3+ dashes before `>`) is invalid XML — a comment
# close must be exactly `-->`. WordPress cache plugins (e.g. iplaysoft's
# `<!--Cached ...--->`) emit this. Only applied as a recovery fallback
# after strict parsing already failed, so the downside of touching a
# `--->` inside CDATA is strictly better than dropping the whole feed.
_EXCESS_COMMENT_DASHES_RE = re.compile(r"-{3,}>")


def _recover_xml(xml_text: str) -> str:
    """Best-effort repair of common real-world feed malformations."""
    repaired = _ILLEGAL_XML_CHARS_RE.sub("", xml_text)
    repaired = _EXCESS_COMMENT_DASHES_RE.sub("-->", repaired)
    return repaired


_RSS_NAMESPACES = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "atom": "http://www.w3.org/2005/Atom",
    # RSS 1.0 (RDF) — items live directly under <rdf:RDF> in this
    # namespace (Impress Watch / ZDNet Japan / legacy nikkei feeds).
    "rss10": "http://purl.org/rss/1.0/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
}


def _find_text(parent: ET.Element, *paths: str) -> str | None:
    """Try several child tag paths and return the first non-empty text."""
    for path in paths:
        el = parent.find(path)
        if el is not None and el.text:
            return el.text.strip()
    return None


def _parse_date(value: str | None) -> datetime | None:
    """Best-effort date parsing for RSS/Atom timestamps.

    Returns the datetime **as parsed** — naive when the feed omits a
    timezone, aware in the feed's own offset when it supplies one. All
    timezone normalization (``default_tz`` for naive values,
    ``tz_override`` for mislabeled feeds, final UTC conversion) happens
    in :func:`_extract_pub_date`, which is the only caller. (Previously
    this function forced naive values to UTC right here, which made the
    ``default_tz`` parameter of ``_extract_pub_date`` dead code — the
    latent bug behind the 2026-08-01 iThome 台湾 +8h incident.)
    """
    if not value:
        return None
    value = value.strip()
    # RFC 2822 / RSS pubDate (e.g. "Sat, 18 Jul 2026 17:30:23 +0800")
    try:
        dt = parsedate_to_datetime(value)
        if dt is not None:
            return dt
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
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    # 36kr style: "2026-07-18 17:30:23  +0800" (two spaces before tz)
    try:
        return datetime.strptime(value.replace("  +", " +"), "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        pass
    # Date-only非标准格式（2026-08-02 official 波实测：hoover/mckinsey 用
    # "July 31, 2026"，fca/fiercehealth 用 "Fri, 31 Jul 2026"——之前解析
    # 失败回退抓取时间，每小时抓的新闻稿源影响约 1 小时误差）。新闻稿类
    # 源日期粒度到天即可，按 naive 返回交给 _extract_pub_date 套 default_tz。
    for fmt in (
        "%B %d, %Y",      # July 31, 2026
        "%a, %d %b %Y",   # Fri, 31 Jul 2026
        "%d %b %Y",       # 31 Jul 2026
        "%d %B %Y",       # 31 July 2026
        "%Y-%m-%d",       # 2026-07-31
    ):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


# 块级元素边界 → 段落换行（2026-08-01 huxiu 段落粘连根治）：剥标签前
# 先把块级边界显式转成 \n\n（<br> 为段内单换行），否则整篇 RSS 全文
# 会被折叠成一段。
_BLOCK_BOUNDARY_RE = re.compile(
    r"</(?:p|div|li|h[1-6]|blockquote|tr|section|article)\s*>",
    re.IGNORECASE,
)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def _strip_html(text: str | None) -> str | None:
    """Drop HTML tags, preserving block-level paragraph breaks as ``\\n\\n``."""
    if not text:
        return None
    import re

    marked = _BR_RE.sub("\n", text)
    marked = _BLOCK_BOUNDARY_RE.sub("\n\n", marked)
    no_tags = re.sub(r"<[^>]+>", " ", marked)
    no_tags = (
        no_tags.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
    )
    # 行内空白折叠但保留段落换行；3+ 连续换行收敛为恰好 \n\n
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in no_tags.split("\n")]
    collapsed = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip("\n")
    return collapsed.strip() or None


def _extract_link(item: ET.Element) -> str | None:
    """Return the canonical URL for an RSS/Atom item."""
    link = _find_text(
        item,
        "link",
        f"{{{_RSS_NAMESPACES['rss10']}}}link",
        f"{{{_RSS_NAMESPACES['atom']}}}link",
    )
    if link:
        return link
    # Atom "link" element has href attribute.
    atom_link = item.find(f"{{{_RSS_NAMESPACES['atom']}}}link")
    if atom_link is not None:
        href = atom_link.get("href")
        if href:
            return href.strip()
    # RSS 1.0: the item's rdf:about attribute is the canonical URL.
    about = item.get(f"{{{_RSS_NAMESPACES['rdf']}}}about")
    if about:
        return about.strip()
    return None


def _extract_guid(item: ET.Element) -> str | None:
    """Return a stable ID for the item, falling back to the link."""
    guid = _find_text(item, "guid", f"{{{_RSS_NAMESPACES['atom']}}}id")
    if guid:
        return guid
    id_el = item.find("id")
    if id_el is not None and id_el.text:
        return id_el.text.strip()
    about = item.get(f"{{{_RSS_NAMESPACES['rdf']}}}about")
    if about:
        return about.strip()
    return _extract_link(item)


def _extract_pub_date(
    item: ET.Element,
    *,
    default_tz: timezone = UTC,
    tz_override: tzinfo | None = None,
) -> datetime | None:
    """Extract and normalize the item's publication timestamp."""
    value = _find_text(
        item,
        "pubDate",
        "pubTime",
        f"{{{_RSS_NAMESPACES['dc']}}}date",
        f"{{{_RSS_NAMESPACES['atom']}}}published",
        f"{{{_RSS_NAMESPACES['atom']}}}updated",
        "published",
        "updated",
    )
    dt = _parse_date(value)
    if dt is None:
        return None
    if tz_override is not None:
        # 部分 feed 的时区标注本身就是错的（2026-08-01 生产事故：
        # nocutnews 的 dc:date 是韩国本地墙钟时间 KST 却标注 "GMT"，
        # 入库后前端 +8 显示成"未来时间"）。对这类 feed 忽略其自带的
        # 时区标注，按发行方本地时区重新解释墙钟时间。
        return dt.replace(tzinfo=None).replace(tzinfo=tz_override).astimezone(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=default_tz)
    return dt.astimezone(UTC)


def parse_rss_items(
    xml_text: str,
    *,
    source: str,
    market: str = "cn_a",
    language: str = "zh",
    default_author: str | None = None,
    max_items: int | None = None,
    default_tz: timezone = UTC,
    tz_override: tzinfo | None = None,
    default_category: str | None = None,
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
        tz_override: When set, the feed's own timezone label is treated
            as wrong and every parsed timestamp's wall time is
            re-interpreted in this timezone instead (see
            :func:`_extract_pub_date`).
        default_category: Fallback ``extra["category"]`` when the item
            itself carries no ``<category>``/``dc:subject`` tag. Used by
            the wechat batch2/3 crawlers to persist the row-level
            taxonomy (macro/strategy/industry/tech/business) that
            ``normalizer._derive_category`` already understands
            (2026-08-02, 学习中心打标接通).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        try:
            root = ET.fromstring(_recover_xml(xml_text))
        except ET.ParseError as exc:
            logger.warning("%s RSS parse error: %s", source, exc)
            return []
        logger.info("%s RSS parsed after malformed-XML recovery", source)

    channel = root.find("channel")
    if channel is not None:
        items = channel.findall("item")
    else:
        # Atom fallback
        items = root.findall(f"{{{_RSS_NAMESPACES['atom']}}}entry")
        if not items:
            items = root.findall("entry")
        if not items:
            # RSS 1.0 (RDF): <item> elements are siblings of <channel>
            # under <rdf:RDF>, in the purl.org rss/1.0 namespace. Bare
            # "item" covers documents that skip the namespace.
            items = root.findall(f"{{{_RSS_NAMESPACES['rss10']}}}item")
            if not items and root.tag.endswith("RDF"):
                items = root.findall("item")

    out: list[RawArticle] = []
    for item in items[:max_items] if max_items else items:
        # Bare names cover RSS 2.0 items; the rss10 variants cover
        # RSS 1.0 (RDF) documents whose default namespace is
        # purl.org/rss/1.0; the Atom-namespace variants cover
        # <feed>-style documents (go.dev, Rust blog, Qiita, Publickey).
        title = _find_text(
            item,
            "title",
            f"{{{_RSS_NAMESPACES['rss10']}}}title",
            f"{{{_RSS_NAMESPACES['atom']}}}title",
        )
        link = _extract_link(item)
        guid = _extract_guid(item)
        if not title or not link:
            logger.debug("%s RSS item skipped: missing title or link", source)
            continue

        description = _find_text(
            item,
            "description",
            "summary",
            f"{{{_RSS_NAMESPACES['rss10']}}}description",
            f"{{{_RSS_NAMESPACES['atom']}}}summary",
        )
        body_html = description
        # Prefer full content:encoded if present; for Atom feeds the
        # richer body lives in <content> (atom namespace).
        content_encoded = item.find(f"{{{_RSS_NAMESPACES['content']}}}encoded")
        if content_encoded is not None and content_encoded.text:
            body_html = content_encoded.text.strip()
        else:
            atom_content = item.find(f"{{{_RSS_NAMESPACES['atom']}}}content")
            if atom_content is not None:
                # <content type="html"> may carry escaped markup as
                # text, or inline XHTML as child elements — serialize
                # the children in that case.
                if atom_content.text and atom_content.text.strip():
                    body_html = atom_content.text.strip()
                elif len(atom_content):
                    body_html = "".join(
                        ET.tostring(child, encoding="unicode", method="html")
                        for child in atom_content
                    ).strip()

        body = _strip_html(body_html)
        author = (
            _find_text(item, "author", f"{{{_RSS_NAMESPACES['dc']}}}creator")
            or _find_text(item, f"{{{_RSS_NAMESPACES['atom']}}}author/{{{_RSS_NAMESPACES['atom']}}}name")
            or default_author
        )
        published_at = _extract_pub_date(
            item, default_tz=default_tz, tz_override=tz_override
        ) or datetime.now(
            tz=UTC
        )

        category = _find_text(item, "category", f"{{{_RSS_NAMESPACES['dc']}}}subject")
        # 条目自身没有 <category> 时回落到调用方给的源级分类
        # （如 wechat batch2/3 行内的 macro/strategy/industry/...）。
        if not category:
            category = default_category

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
