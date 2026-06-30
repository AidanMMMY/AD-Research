"""Anti-scraping primitives for news / disclosure crawlers.

This sub-package provides the shared infra that every source-specific
crawler sits on top of:

- :class:`BaseCrawler` — async HTTP client with UA rotation, retry,
  jitter, rate limit, proxies and stats
- :class:`AsyncTokenBucket` — per-source rate limiter
- :class:`ProxyPool` — round-robin proxy pool (env-driven)
- :class:`BrowserPool` — optional Playwright browser pool (lazy)
- :class:`Stats` — per-source counters and latency percentiles
- :class:`RawArticle` — normalised article dataclass passed between
  crawlers and downstream pipelines

Concrete crawlers (xueqiu, RSS, SEC EDGAR, etc.) live alongside
these primitives and re-export ``BaseCrawler`` / ``RawArticle``.
"""

from app.services.news.crawler.base import (
    DEFAULT_HEADERS,
    DEFAULT_USER_AGENTS,
    BaseCrawler,
    RateLimiter,
    make_client,
)
from app.services.news.crawler.browser import BrowserPool
from app.services.news.crawler.proxy import ProxyPool
from app.services.news.crawler.rate_limiter import AsyncTokenBucket, with_limit
from app.services.news.crawler.stats import Stats, make_stats_registry
from app.services.news.crawler.symbol_extractor import (
    extract_symbols,
    merge_symbols,
)
from app.services.news.crawler.types import RawArticle

__all__ = [
    # Core crawler
    "BaseCrawler",
    "DEFAULT_HEADERS",
    "DEFAULT_USER_AGENTS",
    # Legacy thin wrappers (kept for backwards compatibility)
    "RateLimiter",
    "make_client",
    # Rate limiting
    "AsyncTokenBucket",
    "with_limit",
    # Infra
    "ProxyPool",
    "BrowserPool",
    "Stats",
    "make_stats_registry",
    # Data
    "RawArticle",
    # Symbol extraction (shared by all crawlers)
    "extract_symbols",
    "merge_symbols",
]
