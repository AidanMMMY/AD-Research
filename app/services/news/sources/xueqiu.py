"""Xueqiu (雪球) public-timeline crawler.

This module reads the same JSON endpoints that the public Xueqiu web app
uses; it is **read-only** and never authenticates against user accounts.
The only "credential" required is a valid browser session cookie (see
``xueqiu_auth``).

Endpoint summary (all GET, JSON response):

* ``/v4/statuses/public/timeline.json`` — public posts for a stock symbol.
* ``/statuses/show/{id}.json`` — single post detail (rarely needed; the
  timeline already includes engagement counts and the body).
* ``/statuses/comments.json`` — comments / replies on a post.
* ``/v4/users/show.json`` — user profile (followers, friends, etc.).

Rate limit: the crawler is conservative by default (30 requests / minute
per ``XueqiuCrawler`` instance) and backs off after every failure.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx

from app.services.news.crawler.base import RateLimiter, make_client
from app.services.news.crawler.rate_limiter import AsyncTokenBucket
from app.services.news.crawler.symbol_extractor import extract_symbols as _shared_extract_symbols
from app.services.news.crawler.types import RawArticle
from app.services.news.sources.xueqiu_auth import (
    XUEQIU_BASE_URL,
    XueqiuAuth,
    XueqiuAuthError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Symbol conversion
# ---------------------------------------------------------------------------

# Xueqiu's ``symbol`` parameter uses the form ``SH600519`` / ``SZ000001`` /
# ``HK00700`` / ``BABA`` (no suffix for US). Our internal codes follow the
# Tushare / Finnhub convention ``510050.SH`` / ``AAPL.US`` / ``00700.HK``,
# so we map between the two here.
_US_CODE_RE = re.compile(r"^[A-Z]+$")  # AAPL, TSLA, BABA, ...
_HK_CODE_RE = re.compile(r"^(\d{4,6})\.HK$")


def to_xueqiu_symbol(code: str) -> str:
    """Translate an internal code (e.g. ``600519.SH``) to Xueqiu's form."""
    if not code:
        raise ValueError("empty symbol")
    if "." not in code:
        # Already a raw ticker; assume US form.
        return code.upper()
    raw, _, market = code.rpartition(".")
    market = market.upper()
    if market == "SH":
        return f"SH{raw}"
    if market == "SZ":
        return f"SZ{raw}"
    if market == "BJ":
        return f"BJ{raw}"
    if market == "HK":
        digits = raw.lstrip("0") or "0"
        return f"HK{int(digits):05d}"
    if market == "US":
        return raw.upper()
    # Fall back to the raw ticker; Xueqiu will reject unknown symbols.
    return raw


def _internal_market(code: str) -> str:
    """Map internal code suffix to Agent A's ``market`` bucket."""
    if not code or "." not in code:
        return "cn_a"  # best-effort default
    _, _, suffix = code.rpartition(".")
    suffix = suffix.upper()
    if suffix in {"SH", "SZ", "BJ"}:
        return "cn_a"
    if suffix == "HK":
        return "cn_a"  # share bucket with A-share for now
    return "us"


def extract_symbols(post: dict[str, Any] | str) -> list[str]:
    """Extract the tickers mentioned in a Xueqiu post.

    Wraps :func:`app.services.news.crawler.symbol_extractor.extract_symbols`
    so the Xueqiu-specific code stays in one place. Always returns the
    internal ``XXXX.{SH|SZ|US}`` form. The shared extractor additionally
    adds cashtag / bare-ticker matches from the post body.
    """
    if isinstance(post, dict):
        haystack = " ".join(filter(None, (post.get("title"), post.get("description"), post.get("text"))))
    else:
        haystack = post or ""

    found = _shared_extract_symbols(haystack)

    # Xueqiu users wrap tickers in ``$SH600519$``; the shared extractor
    # already catches ``$TSLA`` (US) but treats ``SH600519`` as a
    # cashtag with a 6-char body which its length cap rejects. Parse
    # those manually here.
    cashtag_re = re.compile(r"\$([A-Z]{2}\d{4,6})(?:\.[A-Z]{1,3})?\$")
    for match in cashtag_re.finditer(haystack):
        raw = match.group(1)
        if raw.startswith("SH"):
            found.add(f"{raw[2:]}.SH")
        elif raw.startswith("SZ"):
            found.add(f"{raw[2:]}.SZ")
        elif raw.startswith("BJ"):
            found.add(f"{raw[2:]}.BJ")
        elif raw.startswith("HK") and raw[2:].isdigit():
            digits = str(int(raw[2:]))
            found.add(f"{int(digits):05d}.HK")

    return sorted(found)


# ---------------------------------------------------------------------------
# Time parsing
# ---------------------------------------------------------------------------


def _parse_xueqiu_time(value: Any) -> datetime | None:
    """Parse Xueqiu's ``created_at`` (epoch millis OR ISO string)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s.isdigit():
            try:
                return datetime.fromtimestamp(int(s) / 1000, tz=timezone.utc)
            except (ValueError, OSError):
                return None
        # Xueqiu's mobile API returns ISO-8601 with Z suffix sometimes.
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass
class RawXueqiuPost:
    """Xueqiu-specific view of a single post (one row per ``id``).

    Mirrors :class:`app.services.news.crawler.types.RawArticle` plus
    Xueqiu-specific extras (``author_id`` / ``author_followers`` /
    ``raw_json``) that don't belong in the shared type.
    """

    source: str = "xueqiu"
    source_id: str = ""
    url: str = ""
    title: str = ""
    body: str = ""
    author: str = ""
    author_id: int | None = None
    author_followers: int | None = None
    published_at: datetime | None = None
    engagement: dict[str, int] = field(default_factory=dict)
    symbols: list[str] = field(default_factory=list)
    market: str = "cn_a"
    language: str = "zh"
    raw_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if isinstance(self.published_at, datetime):
            d["published_at"] = self.published_at.isoformat()
        return d

    def to_article(self) -> RawArticle:
        """Convert to Agent A's shared :class:`RawArticle`."""
        published = self.published_at or datetime.now(tz=timezone.utc)
        return RawArticle(
            source=self.source,
            source_id=self.source_id or None,
            url=self.url,
            title=self.title,
            body=self.body,
            author=self.author or None,
            published_at=published,
            language=self.language,
            market=self.market,
            engagement=dict(self.engagement),
            extra={
                "author_id": self.author_id,
                "author_followers": self.author_followers,
                "symbols": list(self.symbols),
            },
        )


# ---------------------------------------------------------------------------
# Crawler
# ---------------------------------------------------------------------------


class XueqiuCrawler:
    """Fetch public posts / comments / user info from Xueqiu.

    The class is safe to instantiate at import time — no network call is
    made until :meth:`fetch_symbol` (or one of the other fetchers) is
    awaited. The underlying :class:`XueqiuAuth` validates the cookie
    synchronously on construction and will raise :class:`XueqiuAuthError`
    if the env var is missing / malformed.
    """

    #: Default per-minute budget. Caller may override per instance.
    DEFAULT_PER_MINUTE: int = 30

    def __init__(
        self,
        auth: XueqiuAuth | None = None,
        *,
        per_minute: int = 30,
        posts_per_symbol: int = 20,
        comments_per_post: int = 0,
    ) -> None:
        self.auth = auth or XueqiuAuth()
        # `RateLimiter` is the backwards-compat alias for AsyncTokenBucket
        # defined in crawler/base.py. We accept either form.
        bucket: AsyncTokenBucket = RateLimiter(rate=per_minute, period_seconds=60)
        self.rate_limiter = bucket
        self.posts_per_symbol = posts_per_symbol
        self.comments_per_post = comments_per_post

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_symbol(self, symbol: str) -> list[RawXueqiuPost]:
        """Fetch the public timeline for ``symbol``.

        ``symbol`` may be the internal code (``600519.SH``) or the
        Xueqiu-native form (``SH600519``). Returns a list of
        :class:`RawXueqiuPost` sorted newest-first; empty list on
        transient errors.
        """
        if not symbol:
            return []
        xq_symbol = to_xueqiu_symbol(symbol)
        url = f"{XUEQIU_BASE_URL}/v4/statuses/public/timeline.json"
        params = {
            "symbol": xq_symbol,
            "count": self.posts_per_symbol,
            "max_id": -1,
        }
        payload = await self._get_json(url, params=params)
        return self._parse_timeline(payload, primary_symbol=symbol)

    async def fetch_post_detail(self, post_id: int | str) -> dict[str, Any] | None:
        """Fetch a single post by id. Returns the raw JSON dict or None."""
        url = f"{XUEQIU_BASE_URL}/statuses/show/{post_id}.json"
        return await self._get_json(url)

    async def fetch_comments(
        self,
        post_id: int | str,
        *,
        count: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch top-level comments for a post.

        Returns the raw ``comments`` array from the JSON response.
        """
        url = f"{XUEQIU_BASE_URL}/statuses/comments.json"
        params = {
            "id": post_id,
            "count": count or self.comments_per_post or 20,
        }
        payload = await self._get_json(url, params=params)
        if not isinstance(payload, dict):
            return []
        comments = payload.get("comments") or []
        return comments if isinstance(comments, list) else []

    async def fetch_user(self, user_id: int | str) -> dict[str, Any] | None:
        """Fetch a user profile dict. Returns None on 404 / auth failure."""
        url = f"{XUEQIU_BASE_URL}/v4/users/show.json"
        params = {"user_id": user_id}
        return await self._get_json(url, params=params)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        max_attempts: int = 2,
    ) -> dict[str, Any] | None:
        """GET ``url`` as JSON, honouring the rate limiter.

        On 401/403 the cookie is treated as revoked and a single retry
        is performed after re-validating. Other errors return ``None``
        (the caller decides what to do with empty data).
        """
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            await self.rate_limiter.acquire()
            try:
                async with make_client() as client:
                    resp = await client.get(
                        url,
                        params=params,
                        cookies=self.auth.as_httpx_cookies(),
                    )
            except (httpx.HTTPError, asyncio.TimeoutError) as exc:
                last_exc = exc
                logger.warning("Xueqiu GET %s failed (attempt %d): %s", url, attempt, exc)
                if attempt < max_attempts:
                    await asyncio.sleep(60.0)
                    continue
                return None

            if resp.status_code in (401, 403):
                logger.warning(
                    "Xueqiu rejected request (status=%s, url=%s) — refreshing probe",
                    resp.status_code, url,
                )
                self.auth._probe_ok = None  # type: ignore[attr-defined]
                if attempt < max_attempts and await self.auth.is_valid(force=True):
                    continue
                raise XueqiuAuthError(
                    f"Xueqiu auth rejected (status={resp.status_code}). "
                    "Refresh XUEQIU_COOKIE."
                )

            if resp.status_code == 429:
                # Rate-limited by Xueqiu — back off aggressively.
                wait = float(resp.headers.get("Retry-After", "60") or 60)
                logger.warning("Xueqiu 429, sleeping %.0fs", wait)
                await asyncio.sleep(min(wait, 300))
                if attempt < max_attempts:
                    continue
                return None

            if resp.status_code >= 500:
                logger.warning("Xueqiu 5xx (status=%s) on %s", resp.status_code, url)
                if attempt < max_attempts:
                    await asyncio.sleep(60.0)
                    continue
                return None

            if resp.status_code != 200:
                logger.info(
                    "Xueqiu non-200 (status=%s) on %s; skipping",
                    resp.status_code, url,
                )
                return None

            try:
                return resp.json()
            except ValueError:
                logger.info("Xueqiu returned non-JSON body for %s", url)
                return None

        # All attempts failed in a non-recoverable way.
        if last_exc is not None:
            logger.debug("Xueqiu GET %s gave up: %s", url, last_exc)
        return None

    def _parse_timeline(
        self,
        payload: Any,
        *,
        primary_symbol: str,
    ) -> list[RawXueqiuPost]:
        if not isinstance(payload, dict):
            return []
        items = payload.get("list") or []
        if not isinstance(items, list):
            return []
        out: list[RawXueqiuPost] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                post = self._normalise_post(item, primary_symbol=primary_symbol)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Skipping malformed Xueqiu post: %s", exc)
                continue
            if post.source_id:
                out.append(post)
        return out

    def _normalise_post(
        self,
        item: dict[str, Any],
        *,
        primary_symbol: str,
    ) -> RawXueqiuPost:
        post_id = item.get("id")
        source_id = str(post_id) if post_id is not None else ""

        user = item.get("user") or {}
        author = user.get("screen_name") or ""
        author_id = user.get("id")
        followers = user.get("followers_count")

        title = (item.get("title") or "").strip()[:200]
        body = item.get("description") or item.get("text") or ""
        if isinstance(body, str):
            body = body.strip()

        engagement = {
            "likes": int(item.get("like_count") or 0),
            "comments": int(item.get("reply_count") or 0),
            "reposts": int(item.get("retweet_count") or 0),
            "views": int(item.get("view_count") or 0),
        }

        symbols = extract_symbols(item)
        # Always tag the primary symbol that triggered the fetch so
        # downstream consumers can find posts even if the user didn't
        # wrap the ticker in ``$...$``.
        if primary_symbol and primary_symbol not in symbols:
            symbols = [primary_symbol, *symbols]

        url = f"https://xueqiu.com/{source_id}" if source_id else ""

        return RawXueqiuPost(
            source="xueqiu",
            source_id=source_id,
            url=url,
            title=title,
            body=body,
            author=author,
            author_id=author_id,
            author_followers=followers,
            published_at=_parse_xueqiu_time(item.get("created_at")),
            engagement=engagement,
            symbols=symbols,
            market=_internal_market(primary_symbol),
            language="zh",
            raw_json=item,
        )


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


def posts_to_articles(posts: Iterable[RawXueqiuPost]) -> list[RawArticle]:
    """Helper for callers that want the shared :class:`RawArticle` form."""
    return [p.to_article() for p in posts]


def posts_to_dicts(posts: Iterable[RawXueqiuPost]) -> list[dict[str, Any]]:
    """Helper for callers that want plain dicts (e.g. for bulk insert)."""
    return [p.to_dict() for p in posts]
