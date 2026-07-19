"""Per-platform crawlers (Xueqiu, Reddit, Stocktwits, Yahoo, CNBC, SEC, ...)."""

from app.services.news.sources.caixin import CaixinCrawler
from app.services.news.sources.chinanews_finance import ChinanewsFinanceCrawler
from app.services.news.sources.cnbc import CNBCCrawler
from app.services.news.sources.huxiu import HuxiuCrawler
from app.services.news.sources.jiemian import JiemianCrawler
from app.services.news.sources.kr36 import Kr36Crawler
from app.services.news.sources.reddit import (
    DEFAULT_SUBREDDIT_PLAN,
    REDDIT_OAUTH_URL,
    TICKER_SUBREDDITS,
    RedditCrawler,
)
from app.services.news.sources.sec_edgar import (
    SEC_SUBMISSIONS_URL,
    SUPPORTED_FORMS,
    SecEdgarCrawler,
)
from app.services.news.sources.stats_gov import StatsGovCrawler
from app.services.news.sources.wallstreetcn import WallstreetcnCrawler
from app.services.news.sources.wechat_zeping import WechatZepingCrawler
from app.services.news.sources.yahoo_rss import YAHOO_RSS_URL, YahooFinanceCrawler

__all__ = [
    "CaixinCrawler",
    "ChinanewsFinanceCrawler",
    "CNBCCrawler",
    "HuxiuCrawler",
    "JiemianCrawler",
    "Kr36Crawler",
    "RedditCrawler",
    "SecEdgarCrawler",
    "StatsGovCrawler",
    "WallstreetcnCrawler",
    "WechatZepingCrawler",
    "YahooFinanceCrawler",
    "YAHOO_RSS_URL",
    "SEC_SUBMISSIONS_URL",
    "REDDIT_OAUTH_URL",
    "SUPPORTED_FORMS",
    "DEFAULT_SUBREDDIT_PLAN",
    "TICKER_SUBREDDITS",
]
