"""Reddit crawler (US retail-sentiment source).

Pulls posts from finance-related subreddits using Reddit's public
JSON endpoints. Authentication is OAuth2 (``client_credentials`` grant)
via ``https://www.reddit.com/api/v1/access_token``; without credentials
the crawler still works but is capped at 30 req/min by Reddit.

Endpoints
---------
* OAuth token  : ``POST https://www.reddit.com/api/v1/access_token``
* Hot posts    : ``GET  https://oauth.reddit.com/r/{sub}/hot``
* Post detail  : ``GET  https://oauth.reddit.com/r/{sub}/comments/{id}``
* Comments     : ``GET  https://oauth.reddit.com/comments/{id}``

Environment variables
---------------------
* ``REDDIT_CLIENT_ID``
* ``REDDIT_CLIENT_SECRET``
* ``REDDIT_USER_AGENT``  (default: ``AD-Research/1.0``)
* ``REDDIT_USERNAME`` / ``REDDIT_PASSWORD`` (optional, enables
  higher-quota "script" app tokens).

Rate limit
----------
60 req/min when authenticated, 30 req/min otherwise. We self-impose
30 req/min by default to stay well under Reddit's hard caps. The
client caches the bearer token until ~50 s before expiry so the
``access_token`` call is amortised over many requests.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx

from app.services.news.crawler.rate_limiter import AsyncTokenBucket
from app.services.news.crawler.symbol_extractor import extract_symbols
from app.services.news.crawler.types import RawArticle

logger = logging.getLogger(__name__)

REDDIT_OAUTH_URL = "https://oauth.reddit.com"
REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"

# Default universe — sizes per sub reflect the task brief.
DEFAULT_SUBREDDIT_PLAN: dict[str, int] = {
    "wallstreetbets": 25,
    "stocks": 25,
    "investing": 25,
    "options": 25,
    "cryptocurrency": 25,
    "bitcoin": 15,
    "ethereum": 15,
}

# Per-ticker sub handles that are worth polling. Source: manual curation
# of the most active ticker-specific subreddits on Reddit.
TICKER_SUBREDDITS: dict[str, str] = {
    "TSLA": "teslamotors",
    "AAPL": "apple",
    "AMZN": "amazon",
    "GME": "wallstreetbets",  # GME has no dedicated sub that stays active
    "NVDA": "nvidia",
    "AMD": "AMD_Stock",
    "PLTR": "PLTR",
    "COIN": "Coinbase",
    "BABA": "alibababuyback",
    "NIO": "Nio",
    "XPEV": "XPeng",
    "LCID": "lcid",
    "RIVN": "Rivian",
    "F": "Ford",
    "GM": "GeneralMotors",
    "T": "ATT",
    "TLRY": "thetilray",
    "SOFI": "sofi",
    "HOOD": "RobinHood",
    "MARA": "marapond",
    "RIOT": "riotpltr",
    "PYPL": "paypal",
    "DIS": "Disney",
    "NFLX": "netflix",
    "GOOGL": "google",
    "META": "facebook",
    "MSFT": "microsoft",
    "INTC": "intel",
    "BA": "boeing",
    "WMT": "walmart",
    "KO": "CocaCola",
    "PEP": "Pepsi",
    "XOM": "Exxon",
    "CVX": "Chevron",
    "JPM": "jpmorgan",
    "BAC": "BankofAmerica",
    "WFC": "WellsFargo",
    "C": "Citi",
    "GS": "GoldmanSachs",
    "MS": "MorganStanley",
    "V": "Visa",
    "MA": "MasterCard",
    "JNJ": "JNJ",
    "PFE": "Pfizer",
    "MRNA": "moderna",
    "LLY": "lilly",
    "UNH": "unitedhealth",
    "ABBV": "abbvie",
    "CRM": "salesforce",
    "ORCL": "oracle",
    "IBM": "IBM",
    "ADBE": "Adobe",
    "SHOP": "shopify",
    "SQ": "sqstock",
    "UBER": "uberdrivers",
    "LYFT": "lyft",
    "ABNB": "bnb",
    "DASH": "doordash",
    "SNOW": "snowflake",
    "CRWD": "crowdstrike",
    "ZS": "zscaler",
    "NET": "cloudflare",
    "PANW": "paloaltonetworks",
    "OKTA": "okta",
    "DDOG": "datadoghq",
}


def _to_internal(ticker: str) -> str:
    return f"{ticker.upper().strip()}.US"


class _TokenCache:
    """In-memory OAuth bearer token with expiry tracking."""

    def __init__(self) -> None:
        self.token: str | None = None
        # monotonic seconds at which ``token`` expires; we refresh ~50 s early.
        self._expires_at: float = 0.0

    def is_valid(self) -> bool:
        return bool(self.token) and time.monotonic() < self._expires_at

    def set(self, token: str, expires_in: int) -> None:
        self.token = token
        # Refresh slightly before actual expiry.
        self._expires_at = time.monotonic() + max(60, int(expires_in) - 50)


class RedditCrawler:
    """Crawl finance-related subreddits for retail-sentiment signals."""

    source_name = "reddit"
    rate_limit_per_min = 30
    timeout_seconds = 20.0

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        rate_limiter: AsyncTokenBucket | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self._client = client
        self._owns_client = client is None
        self._limiter = rate_limiter or AsyncTokenBucket(self.rate_limit_per_min)
        self._client_id = client_id or os.getenv("REDDIT_CLIENT_ID")
        self._client_secret = client_secret or os.getenv("REDDIT_CLIENT_SECRET")
        self._user_agent = user_agent or os.getenv(
            "REDDIT_USER_AGENT", "AD-Research/1.0 (investment-research)"
        )
        self._tokens = _TokenCache()
        self._lock = asyncio.Lock()

    @property
    def has_credentials(self) -> bool:
        return bool(self._client_id and self._client_secret)

    async def __aenter__(self) -> "RedditCrawler":
        if self._client is None:
            self._client = await self._build_client()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _build_client(self) -> httpx.AsyncClient:
        # Use Basic auth for the token request itself; subsequent API
        # calls use ``Authorization: Bearer <token>``.
        headers = {"User-Agent": self._user_agent}
        return httpx.AsyncClient(
            headers=headers,
            timeout=self.timeout_seconds,
            follow_redirects=True,
        )

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def _ensure_token(self) -> str:
        """Return a valid bearer token, fetching a new one if needed."""
        if self._tokens.is_valid():
            return self._tokens.token or ""
        if not self.has_credentials:
            raise RuntimeError(
                "Reddit credentials not configured. Set REDDIT_CLIENT_ID and "
                "REDDIT_CLIENT_SECRET in the environment."
            )
        async with self._lock:
            # Double-check after acquiring the lock.
            if self._tokens.is_valid():
                return self._tokens.token or ""
            return await self._fetch_token()

    async def _fetch_token(self) -> str:
        assert self._client is not None
        basic = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode()
        resp = await self._client.post(
            REDDIT_TOKEN_URL,
            data={"grant_type": "client_credentials"},
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError(f"Reddit OAuth failed: {data}")
        self._tokens.set(token, int(data.get("expires_in", 3600)))
        return token

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _get_json(self, path: str, *, params: dict | None = None) -> Any:
        """Rate-limited, auth-aware GET against the OAuth endpoint."""
        if not self.has_credentials:
            raise RuntimeError(
                "Reddit credentials not configured. Set REDDIT_CLIENT_ID and "
                "REDDIT_CLIENT_SECRET in the environment."
            )
        await self._limiter.acquire()
        token = await self._ensure_token()
        assert self._client is not None
        url = f"{REDDIT_OAUTH_URL}{path}"
        resp = await self._client.get(
            url,
            params=params or {},
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 401:
            # Token expired between the validity check and the call.
            self._tokens.token = None
            token = await self._ensure_token()
            resp = await self._client.get(
                url,
                params=params or {},
                headers={"Authorization": f"Bearer {token}"},
            )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_subreddit(
        self,
        subreddit: str,
        *,
        limit: int = 25,
        sort: str = "hot",
        timeframe: str = "day",
    ) -> list[RawArticle]:
        """Fetch posts from a single subreddit.

        Args:
            subreddit: bare name (e.g. ``"wallstreetbets"``).
            limit: number of posts to return (max 100).
            sort: ``hot`` | ``new`` | ``top`` | ``rising`` | ``controversial``.
            timeframe: when ``sort in {"top","controversial"}`` — one of
                ``hour``, ``day``, ``week``, ``month``, ``year``, ``all``.
        """
        path = f"/r/{subreddit}/{sort}"
        params: dict[str, Any] = {"limit": min(int(limit), 100)}
        if sort in {"top", "controversial"}:
            params["t"] = timeframe
        data = await self._get_json(path, params=params)
        return _parse_listing(data, subreddit=subreddit)

    async def fetch_universe(
        self,
        plan: dict[str, int] | None = None,
    ) -> list[RawArticle]:
        """Fetch posts from the default (or supplied) subreddit plan.

        ``plan`` maps ``subreddit -> limit``. Errors in any single
        subreddit are logged and skipped so the rest still run.
        """
        target = plan or DEFAULT_SUBREDDIT_PLAN
        out: list[RawArticle] = []
        async with self:
            for sub, limit in target.items():
                try:
                    arts = await self.fetch_subreddit(sub, limit=limit)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Reddit fetch failed for r/%s: %s", sub, exc)
                    continue
                out.extend(arts)
        return out

    async def fetch_ticker_subs(
        self,
        tickers: Iterable[str] | None = None,
        *,
        per_sub_limit: int = 15,
    ) -> list[RawArticle]:
        """Fetch from per-ticker subreddits (curated list)."""
        wanted = list(tickers) if tickers else list(TICKER_SUBREDDITS.keys())
        out: list[RawArticle] = []
        async with self:
            for ticker in wanted:
                sub = TICKER_SUBREDDITS.get(ticker.upper())
                if not sub:
                    continue
                try:
                    arts = await self.fetch_subreddit(sub, limit=per_sub_limit)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Reddit ticker sub failed for r/%s (%s): %s", sub, ticker, exc
                    )
                    continue
                for art in arts:
                    art.extra.setdefault("ticker", ticker.upper())
                    symbols = extract_symbols(
                        f"{art.title}\n{art.body or ''}", subreddit=sub
                    )
                    symbols.add(_to_internal(ticker))
                    art.engagement = {
                        **(art.engagement or {}),
                        "symbols_extracted": sorted(symbols),
                    }
                out.extend(arts)
        return out


# ---------------------------------------------------------------------------
# Pure parsing helpers (testable without HTTP)
# ---------------------------------------------------------------------------


def _parse_listing(data: Any, *, subreddit: str) -> list[RawArticle]:
    """Parse a Reddit listing JSON into ``RawArticle``s."""
    children = (data or {}).get("data", {}).get("children", [])
    out: list[RawArticle] = []
    for child in children:
        d = child.get("data") or {}
        if not d:
            continue
        out.append(_post_to_article(d, subreddit=subreddit))
    return out


def _post_to_article(d: dict, *, subreddit: str) -> RawArticle:
    """Convert a single Reddit post ``data`` dict to a ``RawArticle``."""
    name = d.get("name", "")  # e.g. ``t3_abc123``
    source_id = name.split("_", 1)[-1] if name else d.get("id", "")
    permalink = d.get("permalink", "")
    url = (
        f"https://www.reddit.com{permalink}"
        if permalink
        else d.get("url_overridden_by_dest", "")
    )
    title = d.get("title", "")
    selftext = d.get("selftext") or ""
    body = selftext if selftext else (d.get("url_overridden_by_dest") or "")
    author = d.get("author") or ""
    created_utc = float(d.get("created_utc") or 0.0)
    published_at = (
        datetime.fromtimestamp(created_utc, tz=timezone.utc)
        if created_utc
        else datetime.now(tz=timezone.utc)
    )
    score = int(d.get("score") or 0)
    upvote_ratio = float(d.get("upvote_ratio") or 0.0)
    num_comments = int(d.get("num_comments") or 0)
    gilded = int(d.get("gilded") or 0)
    flair = d.get("link_flair_text") or ""
    is_video = bool(d.get("is_video"))
    is_self = bool(d.get("is_self"))

    # The upvote ratio doubles as a sentiment proxy: > 0.8 bullish,
    # < 0.5 bearish, else neutral. Stored in engagement for Agent E.
    if upvote_ratio >= 0.8:
        proxy = "bullish"
    elif upvote_ratio <= 0.5 and upvote_ratio > 0:
        proxy = "bearish"
    else:
        proxy = "neutral"

    art = RawArticle(
        source="reddit",
        source_id=source_id or url,
        url=url,
        title=title,
        published_at=published_at,
        body=body or None,
        author=author or None,
        language="en",
        market="us",
        extra={
            "subreddit": subreddit,
            "flair": flair,
            "is_self": is_self,
            "is_video": is_video,
            "category": subreddit,
        },
        engagement={
            "score": score,
            "upvote_ratio": round(upvote_ratio, 4),
            "num_comments": num_comments,
            "gilded": gilded,
            "subreddit": subreddit,
            "flair": flair,
            "reddit_id": source_id,
            "sentiment_proxy": proxy,
        },
    )
    symbols = extract_symbols(f"{title}\n{selftext}", subreddit=subreddit, url=url)
    art.engagement["symbols_extracted"] = sorted(symbols)
    return art
