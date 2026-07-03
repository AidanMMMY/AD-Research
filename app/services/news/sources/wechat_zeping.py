"""WeChat Official-Account crawler via a self-hosted wewe-rss instance.

Why wewe-rss
------------
WeChat has no public RSS / API. The community project
`cooderl/wewe-rss <https://github.com/cooderl/wewe-rss>`_ deploys a
small service that signs in to WeChat Reading (微信读书) on your behalf
and exposes each subscribed account as an RSS-JSON feed. The JSON
shape we consume is::

    GET {base}/feeds/{feed_id}.json?limit=30&force=false

::

    {
      "items": [
        {
          "id": "https://...",
          "title": "...",
          "url":   "https://mp.weixin.qq.com/s/...",
          "description": "...",      // summary / first paragraph
          "content_html": "...",      // full HTML body (sometimes truncated)
          "content":      "...",      // plaintext fallback
          "date_published": "2026-07-01T12:34:56.000Z",
          "date_modified":  "...",
          "authors": [{"name": "..."}],
          "image": "..."
        }
      ],
      "status": "ok"
    }

Operational model
-----------------
The crawler is **always silent when wewe-rss is unreachable**: a
missing container, a network blip, or a mis-configured feed id never
crashes the scheduler. It logs once at WARNING level and returns an
empty list, the same way Reddit without credentials behaves. Operators
see the warning on the health page (``last_etl.error_msg``) and can
fix the deployment without restarting the backend.

The actual marketing-content filter lives in
:mod:`app.services.news.filters.wechat_marketing_filter`. The crawler
itself is filter-agnostic — it returns raw posts, the scheduler job
applies the filter and the normalizer persists what survives.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx

from app.config import get_settings
from app.services.news.crawler.types import RawArticle

logger = logging.getLogger(__name__)


# wewe-rss response is RSS-JSON-ish: ``items`` holds the post array.
_DEFAULT_FEED_PATH = "/feeds/{feed_id}.json"


def _build_feed_url(base_url: str, feed_id: str, limit: int) -> str:
    """Build the wewe-rss JSON feed URL.

    Strips any trailing slash from ``base_url`` so we don't end up with
    a ``//`` between host and path.
    """
    base = (base_url or "").rstrip("/")
    path = _DEFAULT_FEED_PATH.format(feed_id=feed_id)
    return f"{base}{path}?limit={int(limit)}"


class WechatZepingCrawler:
    """Crawl WeChat Official-Account posts via wewe-rss.

    Parameters
    ----------
    base_url:
        Override the ``WECHAT_RSS_BASE_URL`` setting.
    feed_id:
        Override the ``WECHAT_RSS_FEED_ID`` setting. Multiple feed ids
        (one per WeChat account) can be passed either as a comma-
        separated string or an iterable.
    timeout_seconds:
        Override the per-request timeout. Default uses the setting.
    client:
        Inject a pre-built ``httpx.AsyncClient`` (for tests).
    """

    source_name = "wechat_zeping"
    market = "cn_a"
    language = "zh"
    rate_limit_per_min = 30

    def __init__(
        self,
        *,
        base_url: str | None = None,
        feed_id: str | Iterable[str] | None = None,
        timeout_seconds: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.wechat_rss_base_url or "").rstrip("/")
        self._feed_ids: list[str] = self._normalize_feed_ids(
            feed_id if feed_id is not None else settings.wechat_rss_feed_id
        )
        self._timeout = float(
            timeout_seconds if timeout_seconds is not None
            else settings.wechat_rss_timeout_seconds
        )
        self._owns_client = client is None
        self._client = client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_recent(self, limit: int = 30) -> list[RawArticle]:
        """Fetch the latest posts from every configured feed.

        Returns a flat list of :class:`RawArticle`. The
        ``extra["feed_id"]`` field tags which wewe-rss feed a post
        came from so the scheduler can attribute it back. Posts from
        feeds that fail are silently dropped (with a WARNING log);
        the rest of the batch keeps flowing.
        """
        if not self._base_url:
            logger.debug(
                "WeChat crawler: WECHAT_RSS_BASE_URL is empty; skipping fetch."
            )
            return []
        if not self._feed_ids:
            logger.debug(
                "WeChat crawler: WECHAT_RSS_FEED_ID is empty; "
                "subscribe to an account in wewe-rss to enable."
            )
            return []

        async with _ClientCtx(self):
            articles: list[RawArticle] = []
            for feed_id in self._feed_ids:
                try:
                    articles.extend(await self._fetch_one_feed(feed_id, limit))
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "WeChat crawler: feed %s failed: %s", feed_id, exc
                    )
            return articles

    async def fetch_feed(self, feed_id: str, limit: int = 30) -> list[RawArticle]:
        """Fetch a single feed by id. Bypasses the configured list.

        Useful for manual backfills from a script — same shape as
        :meth:`fetch_recent` but lets the caller pick the feed.
        """
        if not self._base_url:
            return []
        async with _ClientCtx(self):
            try:
                return await self._fetch_one_feed(feed_id, limit)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "WeChat crawler: feed %s failed: %s", feed_id, exc
                )
                return []

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            headers={
                "Accept": "application/json, text/plain, */*",
                "User-Agent": "AD-Research WeChat RSS crawler/1.0",
            },
        )

    async def _fetch_one_feed(self, feed_id: str, limit: int) -> list[RawArticle]:
        assert self._client is not None
        url = _build_feed_url(self._base_url, feed_id, limit)
        response = await self._client.get(url)
        if response.status_code == 404:
            # wewe-rss returns 404 for unknown / un-subscribed feed ids
            # — treat as a soft "no data" rather than an error.
            logger.warning(
                "WeChat crawler: feed %s returned 404 from %s. "
                "Subscribe the account in wewe-rss first.",
                feed_id,
                self._base_url,
            )
            return []
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning(
                "WeChat crawler: feed %s returned non-JSON payload: %s",
                feed_id,
                exc,
            )
            return []
        if not isinstance(payload, dict):
            return []
        return self._parse_feed_payload(payload, feed_id=feed_id)

    def _parse_feed_payload(
        self, payload: dict[str, Any], *, feed_id: str
    ) -> list[RawArticle]:
        items = payload.get("items")
        if not isinstance(items, list):
            return []
        out: list[RawArticle] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            art = _item_to_raw_article(item, feed_id=feed_id)
            if art is not None:
                out.append(art)
        return out

    @staticmethod
    def _normalize_feed_ids(value: str | Iterable[str] | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return [str(v).strip() for v in value if str(v).strip()]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _ClientCtx:
    """Tiny async context manager that owns the httpx client.

    Lets :meth:`WechatZepingCrawler.fetch_recent` look like
    ``async with self:`` even though we sometimes inject a client that
    the caller owns.
    """

    def __init__(self, crawler: "WechatZepingCrawler") -> None:
        self._crawler = crawler

    async def __aenter__(self) -> httpx.AsyncClient:
        if self._crawler._client is None:
            self._crawler._client = await self._crawler._build_client()
        return self._crawler._client

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._crawler._owns_client and self._crawler._client is not None:
            await self._crawler._client.aclose()
            self._crawler._client = None


_WECHAT_URL_RE = re.compile(r"https?://[^\s\"'<>]+")


def _coerce_published_at(value: Any) -> datetime | None:
    """Parse the variety of date formats wewe-rss has shipped over time."""
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # Normalise trailing Z (Python <3.11 fromisoformat needs +00:00).
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def _coerce_authors(value: Any) -> str | None:
    """wewe-rss authors are a list of ``{"name": "..."}`` dicts."""
    if not value:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        names = [
            str(item.get("name")).strip()
            for item in value
            if isinstance(item, dict) and item.get("name")
        ]
        return ", ".join(n for n in names if n) or None
    return None


def _pick_body(item: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return ``(body_text, body_html)`` from the wewe-rss payload.

    Priority:

    * ``content_html`` if present → body_html
    * ``description`` (always populated) → body_text
    * ``content`` as a last-resort body_text
    """
    body_html = (item.get("content_html") or "").strip() or None
    description = (item.get("description") or "").strip() or None
    content = (item.get("content") or "").strip() or None

    # If we have html, the description is usually a stripped copy of it.
    body_text = description or content
    return body_text, body_html


def _item_to_raw_article(
    item: dict[str, Any], *, feed_id: str
) -> RawArticle | None:
    """Map a wewe-rss item dict into a :class:`RawArticle`.

    Returns ``None`` when the item is missing the required fields
    (title / url). ``date_published`` falls back to
    ``date_modified``, then to ``datetime.now(UTC)``.
    """
    title = (item.get("title") or "").strip()
    url = (item.get("url") or "").strip()
    if not title or not url:
        return None

    source_id_raw = item.get("id") or url
    # The ``id`` field on wewe-rss is sometimes the same as ``url``;
    # when it isn't, keep it — it's the canonical post id.
    source_id = str(source_id_raw).strip() or url

    published_at = (
        _coerce_published_at(item.get("date_published"))
        or _coerce_published_at(item.get("date_modified"))
        or datetime.now(tz=timezone.utc)
    )

    body_text, body_html = _pick_body(item)
    author = _coerce_authors(item.get("authors"))

    extra: dict[str, Any] = {
        "feed_id": feed_id,
        "image": item.get("image"),
    }
    # If description is empty but content_html is rich, surface the html
    # so the normalizer can build a non-empty summary.
    if not body_text and body_html:
        body_text = _first_paragraph_from_html(body_html)

    return RawArticle(
        source="wechat_zeping",
        source_id=source_id[:512],  # column is String(512) on NewsArticle
        url=url[:1000],
        title=title[:1000],
        published_at=published_at,
        body=body_text[:8000] if body_text else None,
        body_html=body_html[:16000] if body_html else None,
        author=author,
        language="zh",
        market="cn_a",
        extra=extra,
    )


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _first_paragraph_from_html(html: str) -> str | None:
    """Cheap html→text for the summary column."""
    if not html:
        return None
    text = _HTML_TAG_RE.sub(" ", html)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text[:8000] if text else None