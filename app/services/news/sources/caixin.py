"""财新网最新文章 crawler.

Uses the public Caixin scroll/index API that powers its homepage. No
authentication required.

Endpoint
--------
``https://gateway.caixin.com/api/dataplatform/scroll/index``

The response has ``code=0`` and ``data.articleList`` where each article
contains ``contentId``, ``title``, ``summary``, ``author``, ``url`` and
``time`` (epoch milliseconds).

Rate limit
----------
30 req/min self-imposed. The endpoint is used by Caixin's own frontend.
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

CAIXIN_LATEST_URL = "https://gateway.caixin.com/api/dataplatform/scroll/index"


class CaixinCrawler(BaseCrawler):
    """Crawl Caixin latest articles."""

    source_name = "caixin"
    rate_limit_per_min = 30
    market = "cn_a"
    language = "zh"

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("rate_limit_per_min", self.rate_limit_per_min)
        super().__init__(**kwargs)

    async def crawl(self) -> list[RawArticle]:
        if not await is_robots_allowed(CAIXIN_LATEST_URL):
            logger.warning("%s blocked by robots.txt", self.source_name)
            return []
        response = await self.fetch(CAIXIN_LATEST_URL)
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
                logger.warning("Caixin normalize failed: %s", exc)
        db.commit()
        return inserted

    def _parse_payload(self, text: str) -> list[RawArticle]:
        try:
            data = json.loads(text)
        except (TypeError, ValueError) as exc:
            logger.warning("Caixin JSON parse error: %s", exc)
            return []
        if not isinstance(data, dict):
            return []
        code = data.get("code")
        if code != 0:
            logger.warning("Caixin API returned code=%s", code)
            return []
        article_list = (data.get("data") or {}).get("articleList") or []
        if not isinstance(article_list, list):
            return []

        out: list[RawArticle] = []
        for item in article_list:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            if not title or not url:
                continue
            summary = (item.get("summary") or "").strip()
            author = (item.get("author") or "").strip()
            content_id = (item.get("contentId") or item.get("appContentId") or url)
            channel_obj = item.get("channelObject") or {}
            channel_name = (channel_obj.get("name") or "").strip()
            published_at = self._parse_ms_time(item.get("time"))
            out.append(
                RawArticle(
                    source=self.source_name,
                    source_id=str(content_id),
                    url=url,
                    title=title,
                    body=summary or None,
                    body_html=None,
                    author=author or None,
                    published_at=published_at,
                    language=self.language,
                    market=self.market,
                    extra={
                        "channel": channel_name,
                        "media_name": (item.get("mediaName") or "").strip(),
                        "keyword": (item.get("keyword") or "").strip(),
                    },
                )
            )
        return out

    @staticmethod
    def _parse_ms_time(value: Any) -> datetime:
        try:
            ms = int(value)
            if ms > 0:
                return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
        except (TypeError, ValueError):
            pass
        return datetime.now(tz=timezone.utc)
