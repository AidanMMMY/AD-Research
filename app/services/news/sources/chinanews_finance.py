"""中国新闻网财经 RSS crawler.

Official public RSS feed, no authentication.

Endpoint
--------
``https://www.chinanews.com.cn/rss/finance.xml``

Rate limit
----------
20 req/min self-imposed.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.news.crawler.base import BaseCrawler, _Response
from app.services.news.crawler.robots import is_robots_allowed
from app.services.news.crawler.types import RawArticle
from app.services.news.sources.rss_common import parse_rss_items

logger = logging.getLogger(__name__)

CHINANEWS_FINANCE_RSS_URL = "https://www.chinanews.com.cn/rss/finance.xml"


class ChinanewsFinanceCrawler(BaseCrawler):
    """Crawl ChinaNews finance RSS feed."""

    source_name = "chinanews_finance"
    rate_limit_per_min = 20
    market = "cn_a"
    language = "zh"

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("rate_limit_per_min", self.rate_limit_per_min)
        super().__init__(**kwargs)

    async def crawl(self) -> list[RawArticle]:
        if not await is_robots_allowed(CHINANEWS_FINANCE_RSS_URL):
            logger.warning("%s blocked by robots.txt", self.source_name)
            return []
        response = await self.fetch(CHINANEWS_FINANCE_RSS_URL)
        return await self.parse(response)

    async def parse(self, response: _Response) -> list[RawArticle]:  # type: ignore[override]
        return parse_rss_items(
            response.text,
            source=self.source_name,
            market=self.market,
            language=self.language,
            default_author="中国新闻网",
            max_items=50,
        )

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
                logger.warning("Chinanews finance normalize failed: %s", exc)
        db.commit()
        return inserted
