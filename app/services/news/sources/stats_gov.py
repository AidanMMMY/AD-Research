"""国家统计局数据发布 RSS crawler.

Official public RSS feeds from stats.gov.cn, no authentication. These feeds
publish macro data releases (``sj/zxfb``) and data interpretations
(``sj/sjjd``), which are useful for macro / policy research.

Endpoints
---------
- Latest releases: ``https://www.stats.gov.cn/sj/zxfb/rss.xml``
- Data interpretation: ``https://www.stats.gov.cn/sj/sjjd/rss.xml``

Rate limit
----------
10 req/min self-imposed. The feeds are large (multi-MB), so we only fetch
the latest releases endpoint and keep the last 50 items.
"""

from __future__ import annotations

import logging
from typing import Any
from zoneinfo import ZoneInfo

from app.services.news.crawler.base import BaseCrawler, _Response
from app.services.news.crawler.robots import is_robots_allowed
from app.services.news.crawler.types import RawArticle
from app.services.news.sources.rss_common import parse_rss_items

logger = logging.getLogger(__name__)

STATS_GOV_LATEST_URL = "https://www.stats.gov.cn/sj/zxfb/rss.xml"
STATS_GOV_INTERPRET_URL = "https://www.stats.gov.cn/sj/sjjd/rss.xml"


class StatsGovCrawler(BaseCrawler):
    """Crawl stats.gov.cn macro data RSS feeds."""

    source_name = "stats_gov"
    rate_limit_per_min = 10
    market = "macro"
    language = "zh"
    # The zxfb feed is multi-MB; the default 20s timeout is not enough on
    # slow links, and every retry re-downloads the whole body.
    request_timeout = 60.0

    def __init__(self, *, interpretation: bool = False, **kwargs: Any) -> None:
        kwargs.setdefault("rate_limit_per_min", self.rate_limit_per_min)
        super().__init__(**kwargs)
        self._feed_url = STATS_GOV_INTERPRET_URL if interpretation else STATS_GOV_LATEST_URL
        self._max_items = 50

    async def crawl(self) -> list[RawArticle]:
        if not await is_robots_allowed(self._feed_url):
            logger.warning("%s blocked by robots.txt", self.source_name)
            return []
        response = await self.fetch(self._feed_url)
        return await self.parse(response)

    async def parse(self, response: _Response) -> list[RawArticle]:  # type: ignore[override]
        articles = parse_rss_items(
            response.text,
            source=self.source_name,
            market=self.market,
            language=self.language,
            default_author="国家统计局",
            max_items=self._max_items,
            default_tz=ZoneInfo("Asia/Shanghai"),
        )
        # Tag the provenance of each item so consumers can distinguish
        # raw releases from interpretation articles.
        feed_type = "interpretation" if self._feed_url == STATS_GOV_INTERPRET_URL else "latest"
        for art in articles:
            art.extra = {"feed_type": feed_type, **art.extra}
        return articles

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
                logger.warning("StatsGov normalize failed: %s", exc)
        db.commit()
        return inserted
