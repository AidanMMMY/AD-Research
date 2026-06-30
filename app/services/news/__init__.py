"""News and financial media crawler services package.

Provides anti-scraping primitives (rate limiting, proxy rotation,
browser pool) and concrete source crawlers for various financial
news / disclosure feeds.
"""

from app.services.news.crawler import (
    AsyncTokenBucket,
    ProxyPool,
    RawArticle,
    Stats,
)

# ``BaseCrawler`` / ``BrowserPool`` are forward-declared by Agent A. They
# are imported lazily so that downstream agents (Xueqiu / Reddit / A股 RSS)
# can import from this package even before Agent A lands the full
# implementation. Direct callers should prefer
# ``from app.services.news.crawler import ...`` instead.
try:  # pragma: no cover - import-time branch
    from app.services.news.crawler import BaseCrawler  # type: ignore
except ImportError:  # pragma: no cover
    BaseCrawler = None  # type: ignore[assignment]

try:  # pragma: no cover - import-time branch
    from app.services.news.crawler import BrowserPool  # type: ignore
except ImportError:  # pragma: no cover
    BrowserPool = None  # type: ignore[assignment]

__all__ = [
    "BaseCrawler",
    "AsyncTokenBucket",
    "ProxyPool",
    "BrowserPool",
    "Stats",
    "RawArticle",
]
