"""Sina Finance roll-news crawler.

Sina exposes a free, public JSON "roll" feed that aggregates the
finance channel. No API key, no auth — the endpoint is the one used
by Sina's own finance portal.

Endpoint
--------
``https://feed.mix.sina.com.cn/api/roll/get``
Query params:
  pageid=153, lid=2516, num=50, versionNumber=1.2.4, page=1

The response is a JSON object with a ``result.data`` array of news
items. Each item has ``title``, ``url``, ``ctime`` (unix seconds),
``intro``, ``media_name``, etc.

Rate limit
----------
Self-imposed 30 req/min via :attr:`rate_limit_per_min`. Sina's edge
tolerates a small multiple of that for a single client. We poll one
page per call (num=50) which is enough for a daily news feed.

Coverage
--------
Sina Finance 财经频道 — macro / 滚动 / 上市公司 / 港股 / 美股 / 基金
cross-section (the lid=2516 channel picks "财经-焦点"). For more
focused feeds (A股 only, or a particular sub-channel) override
``pageid`` / ``lid`` on the constructor.
"""

from __future__ import annotations

import json as _json
import logging
from datetime import datetime, timezone
from typing import Any

from app.services.news.crawler.base import BaseCrawler, _Response
from app.services.news.crawler.types import RawArticle

logger = logging.getLogger(__name__)

SINA_ROLL_URL = "https://feed.mix.sina.com.cn/api/roll/get"

# Default channel — 财经焦点 (Finance Highlights). Override per call
# if you want a sub-channel.
DEFAULT_PARAMS: dict[str, Any] = {
    "pageid": 153,
    "lid": 2516,
    "num": 50,
    "versionNumber": "1.2.4",
    "page": 1,
}

# Extra headers — Sina's edge looks at the Referer.
SINA_EXTRA_HEADERS: dict[str, str] = {
    "Referer": "https://finance.sina.com.cn/",
    "Origin": "https://finance.sina.com.cn",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept": "application/json, text/plain, */*",
}


class SinaCrawler(BaseCrawler):
    """Crawl Sina Finance roll-news feed."""

    source_name = "sina_finance"
    rate_limit_per_min = 30
    market = "cn_a"
    language = "zh"

    def __init__(
        self,
        *,
        default_params: dict[str, Any] | None = None,
        **kwargs,  # forwarded to BaseCrawler
    ) -> None:
        kwargs.setdefault("rate_limit_per_min", self.rate_limit_per_min)
        super().__init__(**kwargs)
        # Copy to keep per-instance state (so callers can mutate freely).
        self._default_params: dict[str, Any] = dict(default_params or DEFAULT_PARAMS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def crawl(self, *, page: int = 1, num: int = 50) -> list[RawArticle]:
        """Fetch one page of Sina Finance roll news."""
        params = dict(self._default_params)
        params["page"] = page
        params["num"] = num
        # The base class ``crawl`` is GET-with-URL; we go through
        # ``fetch`` directly so we can pass query params + Referer.
        response = await self.fetch(SINA_ROLL_URL, params=params, headers=SINA_EXTRA_HEADERS)
        return self._parse_payload(_safe_json(response.text))

    async def parse(self, response) -> list[RawArticle]:  # type: ignore[override]
        """Parse a JSON dict (or :class:`_Response`) into :class:`RawArticle`."""
        if isinstance(response, _Response):
            return self._parse_payload(_safe_json(response.text))
        if isinstance(response, dict):
            return self._parse_payload(response)
        return []

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
                logger.warning("Sina normalize failed: %s", exc)
                continue
            if article is not None:
                inserted += 1
        db.commit()
        return inserted

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _parse_payload(self, payload) -> list[RawArticle]:
        if not isinstance(payload, dict):
            return []
        result = payload.get("result") or {}
        data = result.get("data") or []
        if not isinstance(data, list):
            return []
        out: list[RawArticle] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            if not title or not url:
                continue
            published_at = _parse_ctime(item.get("ctime")) or datetime.now(tz=timezone.utc)
            intro = (item.get("intro") or "").strip() or None
            media_name = (item.get("media_name") or "").strip() or None
            source_id = (item.get("id") or url).strip()

            art = RawArticle(
                source=self.source_name,
                source_id=str(source_id),
                url=url,
                title=title,
                published_at=published_at,
                body=intro,
                body_html=None,
                author=media_name,
                language=self.language,
                market=self.market,
                extra={
                    "media_name": media_name,
                    "channel": item.get("channel"),
                    "comment_count": item.get("comment_count"),
                },
            )
            out.append(art)
        return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_json(value: str | None) -> dict:
    if not value:
        return {}
    try:
        data = _json.loads(value)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _parse_ctime(value) -> datetime | None:
    """Parse a Sina ``ctime`` (Unix seconds, occasionally a string).

    Returns a UTC-aware datetime or ``None`` on failure.
    """
    if value is None or value == "":
        return None
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
