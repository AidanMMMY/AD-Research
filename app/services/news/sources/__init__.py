"""Per-platform crawlers (Xueqiu, Reddit, Stocktwits, Yahoo, CNBC, SEC, ...)."""

from app.services.news.sources.cnbc import CNBCCrawler
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
from app.services.news.sources.yahoo_rss import YAHOO_RSS_URL, YahooFinanceCrawler

__all__ = [
    "CNBCCrawler",
    "RedditCrawler",
    "SecEdgarCrawler",
    "YahooFinanceCrawler",
    "YAHOO_RSS_URL",
    "SEC_SUBMISSIONS_URL",
    "REDDIT_OAUTH_URL",
    "SUPPORTED_FORMS",
    "DEFAULT_SUBREDDIT_PLAN",
    "TICKER_SUBREDDITS",
]
