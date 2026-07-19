"""华尔街见闻 7x24 快讯 crawler.

Uses the public Wallstreetcn "lives" API. No authentication required.

Endpoint
--------
``https://api-one.wallstcn.com/apiv1/content/lives?channel=global-channel&limit=50``

The endpoint returns a JSON envelope with ``data.items``. Each item has a
numeric ``id``, ``title``, ``content_text``, ``content`` (HTML),
``display_time`` (Unix seconds), ``uri`` and author metadata.

Rate limit
----------
Self-imposed 60 req/min. The API is used by Wallstreetcn's own frontend, so
this level is polite and sustainable.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.services.news.crawler.base import BaseCrawler, _Response
from app.services.news.crawler.robots import is_robots_allowed
from app.services.news.crawler.types import RawArticle

logger = logging.getLogger(__name__)

WALLSTREETCN_LIVES_URL = (
    "https://api-one.wallstcn.com/apiv1/content/lives"
    "?channel=global-channel&limit=50"
)


class WallstreetcnCrawler(BaseCrawler):
    """Crawl Wallstreetcn 7x24 live news."""

    source_name = "wallstreetcn"
    rate_limit_per_min = 60
    market = "cn_a"
    language = "zh"

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("rate_limit_per_min", self.rate_limit_per_min)
        super().__init__(**kwargs)

    async def crawl(self) -> list[RawArticle]:
        if not await is_robots_allowed(WALLSTREETCN_LIVES_URL):
            logger.warning("%s blocked by robots.txt", self.source_name)
            return []
        response = await self.fetch(WALLSTREETCN_LIVES_URL)
        return self._parse_payload(response.text)

    async def parse(self, response: _Response) -> list[RawArticle]:  # type: ignore[override]
        return self._parse_payload(response.text)

    async def run(self, db: Any) -> int:
        from app.services.news.normalizer import NewsNormalizer

        raw_articles = await self.crawl()
        if not raw_articles:
            return 0
        normalizer = NewsNormalizer(db)
        inserted = 0
        for raw in raw_articles:
            try:
                article = normalizer.normalize(raw)
                if article is not None:
                    inserted += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Wallstreetcn normalize failed: %s", exc)
        db.commit()
        return inserted

    def _parse_payload(self, text: str) -> list[RawArticle]:
        try:
            data = json.loads(text)
        except (TypeError, ValueError) as exc:
            logger.warning("Wallstreetcn JSON parse error: %s", exc)
            return []
        if not isinstance(data, dict):
            return []
        items = (data.get("data") or {}).get("items") or []
        if not isinstance(items, list):
            return []

        out: list[RawArticle] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            url = (item.get("uri") or "").strip()
            if not title or not url:
                continue
            content_text = (item.get("content_text") or "").strip()
            content_html = (item.get("content") or "").strip()
            content_more = (item.get("content_more") or "").strip()
            body_html = content_html or content_more
            published_at = self._parse_display_time(item.get("display_time"))
            author = ((item.get("author") or {}).get("display_name") or "").strip()
            source_id = str(item.get("id") or url)
            channels = item.get("channels")
            out.append(
                RawArticle(
                    source=self.source_name,
                    source_id=source_id,
                    url=url,
                    title=title,
                    body=content_text or self.strip_html(body_html),
                    body_html=body_html or None,
                    author=author or None,
                    published_at=published_at,
                    language=self.language,
                    market=self.market,
                    extra={
                        "channels": channels if isinstance(channels, list) else [],
                        "type": item.get("type"),
                    },
                )
            )
        return out

    @staticmethod
    def _parse_display_time(value: Any) -> datetime:
        try:
            seconds = int(value)
            if seconds > 0:
                return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (TypeError, ValueError):
            pass
        return datetime.now(tz=timezone.utc)
