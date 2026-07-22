"""Parameterized RSS crawler plus thin per-source subclasses.

Why this module exists
----------------------
Most RSS sources differ only in feed URL, market bucket, language and
display author. Instead of duplicating the ``kr36.py`` skeleton a dozen
times, :class:`SimpleRssCrawler` parameterizes the whole flow (robots
check -> fetch -> :func:`parse_rss_items`) and each concrete source is a
thin subclass that only sets class attributes.

All feeds listed here are official public RSS/Atom endpoints, no
authentication required.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from app.services.news.crawler.base import BaseCrawler, _Response
from app.services.news.crawler.robots import is_robots_allowed
from app.services.news.crawler.types import RawArticle
from app.services.news.sources.rss_common import parse_rss_items

logger = logging.getLogger(__name__)


class SimpleRssCrawler(BaseCrawler):
    """Generic single-feed RSS crawler.

    Subclasses set ``feed_url`` (and typically ``source_name``,
    ``market``, ``language``, ``default_author``) — everything else is
    handled here, mirroring the behaviour of ``kr36.py``.
    """

    source_name: ClassVar[str] = "simple_rss"
    feed_url: ClassVar[str] = ""
    market: ClassVar[str] = "us"
    language: ClassVar[str] = "en"
    default_author: ClassVar[str | None] = None
    max_items: ClassVar[int] = 50
    rate_limit_per_min: ClassVar[int] = 20

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("rate_limit_per_min", self.rate_limit_per_min)
        super().__init__(**kwargs)

    async def crawl(self) -> list[RawArticle]:  # type: ignore[override]
        if not await is_robots_allowed(self.feed_url):
            logger.warning("%s blocked by robots.txt", self.source_name)
            return []
        response = await self.fetch(self.feed_url)
        return await self.parse(response)

    async def parse(self, response: _Response) -> list[RawArticle]:
        return parse_rss_items(
            response.text,
            source=self.source_name,
            market=self.market,
            language=self.language,
            default_author=self.default_author,
            max_items=self.max_items,
        )


class MarketWatchCrawler(SimpleRssCrawler):
    """MarketWatch top stories RSS."""

    source_name = "marketwatch"
    feed_url = "https://feeds.marketwatch.com/marketwatch/topstories/"
    default_author = "MarketWatch"


class ZeroHedgeCrawler(SimpleRssCrawler):
    """ZeroHedge RSS via FeedBurner."""

    source_name = "zerohedge"
    feed_url = "https://feeds.feedburner.com/zerohedge/feed"
    default_author = "ZeroHedge"


class SeekingAlphaCrawler(SimpleRssCrawler):
    """Seeking Alpha market currents RSS."""

    source_name = "seekingalpha"
    feed_url = "https://seekingalpha.com/market_currents.xml"
    default_author = "Seeking Alpha"


class FtCrawler(SimpleRssCrawler):
    """Financial Times homepage RSS."""

    source_name = "ft"
    feed_url = "https://www.ft.com/rss/home"
    default_author = "Financial Times"


class InvestingCrawler(SimpleRssCrawler):
    """Investing.com stock market news RSS."""

    source_name = "investing"
    feed_url = "https://www.investing.com/rss/news_25.rss"
    default_author = "Investing.com"


class DecryptCrawler(SimpleRssCrawler):
    """Decrypt crypto news RSS."""

    source_name = "decrypt"
    feed_url = "https://decrypt.co/feed"
    market = "crypto"
    default_author = "Decrypt"


class FederalReserveCrawler(SimpleRssCrawler):
    """US Federal Reserve press releases RSS."""

    source_name = "federal_reserve"
    feed_url = "https://www.federalreserve.gov/feeds/press_all.xml"
    default_author = "Federal Reserve"


class EcbCrawler(SimpleRssCrawler):
    """European Central Bank press releases RSS."""

    source_name = "ecb"
    feed_url = "https://www.ecb.europa.eu/rss/press.html"
    default_author = "ECB"


class BankOfEnglandCrawler(SimpleRssCrawler):
    """Bank of England news RSS."""

    source_name = "bankofengland"
    feed_url = "https://www.bankofengland.co.uk/rss/news"
    default_author = "Bank of England"


class BbcBusinessCrawler(SimpleRssCrawler):
    """BBC Business news RSS."""

    source_name = "bbc_business"
    feed_url = "https://feeds.bbci.co.uk/news/business/rss.xml"
    default_author = "BBC"


class ArxivQfinCrawler(SimpleRssCrawler):
    """arXiv quantitative finance RSS (Atom-flavoured, low volume)."""

    source_name = "arxiv_qfin"
    feed_url = "https://arxiv.org/rss/q-fin"
    default_author = "arXiv"
    max_items = 30
    rate_limit_per_min = 10
