"""Generic async crawler base class.

Subclasses implement ``parse(response)``. The base takes care of:

- A rotating pool of desktop User-Agents (15 entries)
- Per-source async rate limiting (token bucket)
- Optional proxy rotation (round-robin / env-driven)
- Exponential backoff with jitter on transient failure
- Per-source Stats (success / failed / timeout / blocked / latency)
- A standard response wrapper (``_Response``) so subclasses can
  write a single ``parse`` implementation regardless of whether
  the response came from httpx or Playwright.

The class is usable as an async context manager::

    async with MyCrawler() as crawler:
        articles = await crawler.crawl("https://example.com/feed")

Each ``crawl`` call returns a list of :class:`RawArticle`.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, ClassVar

import httpx

from app.services.news.crawler.proxy import ProxyPool
from app.services.news.crawler.rate_limiter import AsyncTokenBucket
from app.services.news.crawler.stats import Stats
from app.services.news.crawler.types import RawArticle

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Backwards-compat aliases.
# Older code (and the pre-Agent-A package __init__) imported
# ``RateLimiter`` and ``make_client`` from this module. Concrete crawlers
# and the existing ``__init__`` still rely on those names. We keep them
# as thin wrappers around the new primitives.
# ---------------------------------------------------------------------------
RateLimiter = AsyncTokenBucket  # type: ignore[misc]  # noqa: F811


@asynccontextmanager
async def make_client(
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> AsyncIterator[httpx.AsyncClient]:
    """Yield a configured ``httpx.AsyncClient`` and close it on exit.

    Retained for backwards compatibility — prefer
    :class:`BaseCrawler` for new code.
    """
    merged = {**DEFAULT_HEADERS, **(headers or {})}
    async with httpx.AsyncClient(
        headers=merged,
        timeout=timeout,
        follow_redirects=True,
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# Desktop User-Agent pool (15 entries covering the major evergreen browsers
# across Windows / macOS / Linux desktop platforms).
# ---------------------------------------------------------------------------
DEFAULT_USER_AGENTS: list[str] = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    # Chrome on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0",
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:131.0) Gecko/20100101 Firefox/131.0",
    # Firefox on Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0",
    # Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    # Opera
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 OPR/117.0.0.0",
    # Brave (looks identical to Chrome to most anti-bot systems)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]


# Headers that a regular browser would send — kept lean to avoid leaking
# automation indicators but broad enough to render the page plausibly.
DEFAULT_HEADERS: dict[str, str] = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


class _Response:
    """Minimal response wrapper exposed to subclasses via ``parse``.

    Exposes ``url``, ``text``, ``content``, ``status_code`` and
    ``headers`` so a parser doesn't need to know whether the bytes
    came from httpx or Playwright.
    """

    __slots__ = ("url", "text", "content", "status_code", "headers")

    def __init__(
        self,
        url: str,
        text: str,
        content: bytes,
        status_code: int,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.url = url
        self.text = text
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}


class BaseCrawler(ABC):
    """Abstract anti-scraping-aware HTTP client for a single source.

    Subclasses set ``source_name`` (string identifier used in stats
    and logs) and implement :meth:`parse`. Everything else — UA
    rotation, retries, proxy / rate / jitter plumbing — is provided.

    Class-level configuration:

    - ``rate_limit_per_min`` — applied via :class:`AsyncTokenBucket`.
      Override per subclass as needed.
    - ``use_browser`` — set to ``True`` when Playwright is required
      (JS-only / Cloudflare sites). The base implementation still
      uses httpx; subclasses opt into a browser by calling
      :meth:`fetch_via_browser` instead of :meth:`fetch`.
    """

    source_name: ClassVar[str] = "base"
    rate_limit_per_min: ClassVar[int] = 30
    use_browser: ClassVar[bool] = False

    # ---- retry knobs (per subclass if needed) ----
    max_retries: ClassVar[int] = 5
    backoff_base: ClassVar[float] = 0.5
    backoff_cap: ClassVar[float] = 30.0
    jitter_min: ClassVar[float] = 0.5
    jitter_max: ClassVar[float] = 2.0
    request_timeout: ClassVar[float] = 20.0

    # ---- class-shared pools (created lazily) ----
    _proxy_pool: ClassVar[ProxyPool | None] = None

    def __init__(
        self,
        *,
        rate_limit_per_min: int | None = None,
        proxies: list[str] | None = None,
        stats: Stats | None = None,
        client: httpx.AsyncClient | None = None,
        user_agents: list[str] | None = None,
    ) -> None:
        self.rate_limit_per_min_override = rate_limit_per_min
        self._rate_limiter: AsyncTokenBucket | None = None
        self._stats = stats or Stats()
        self._user_agents = list(user_agents or DEFAULT_USER_AGENTS)
        if not self._user_agents:
            raise ValueError("user_agents must not be empty")

        if proxies is not None:
            self._proxy_override = ProxyPool(proxies)
        else:
            self._proxy_override = None

        self._client = client  # if the caller supplied one, we reuse it
        self._owns_client = client is None
        self._entered = False
        self._active_proxy: str | None = None

    # ------------------------------------------------------------------
    # Class-level proxy pool (shared so the env is honoured once)
    # ------------------------------------------------------------------
    @classmethod
    def _shared_proxy_pool(cls) -> ProxyPool:
        if cls._proxy_pool is None:
            cls._proxy_pool = ProxyPool.from_env()
        return cls._proxy_pool

    @property
    def proxy_pool(self) -> ProxyPool:
        if self._proxy_override is not None:
            return self._proxy_override
        return self._shared_proxy_pool()

    # ------------------------------------------------------------------
    # Context manager — owning the AsyncClient
    # ------------------------------------------------------------------
    async def __aenter__(self) -> "BaseCrawler":
        if self._client is None:
            timeout = httpx.Timeout(self.request_timeout)
            # ``trust_env=True`` lets the underlying urllib loop pick up
            # HTTP_PROXY/HTTPS_PROXY env vars when no proxy is set on
            # the request itself.
            kwargs: dict[str, Any] = dict(
                timeout=timeout,
                follow_redirects=True,
                headers=dict(DEFAULT_HEADERS),
                trust_env=True,
            )
            # HTTP/2 is a nice-to-have; degrade silently when ``h2`` is
            # missing so the crawler still works in minimal environments.
            try:
                import h2  # type: ignore[import-not-found]  # noqa: F401

                kwargs["http2"] = True
            except Exception:  # noqa: BLE001
                pass
            self._client = httpx.AsyncClient(**kwargs)
        self._entered = True
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self._entered = False
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Rate limit accessors
    # ------------------------------------------------------------------
    def _get_rate_limiter(self) -> AsyncTokenBucket:
        if self._rate_limiter is None:
            rate = self.rate_limit_per_min_override or self.rate_limit_per_min
            # Small initial burst (1/4 of the bucket) so the very first
            # request can fire immediately without violating the cap.
            initial = max(1, rate // 4)
            self._rate_limiter = AsyncTokenBucket(
                rate=rate, period_seconds=60, initial_tokens=initial
            )
        return self._rate_limiter

    @property
    def stats(self) -> Stats:
        return self._stats

    # ------------------------------------------------------------------
    # Headers / proxy helpers
    # ------------------------------------------------------------------
    def _pick_user_agent(self) -> str:
        return random.choice(self._user_agents)

    def _build_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        ua = self._pick_user_agent()
        h = dict(DEFAULT_HEADERS)
        h["User-Agent"] = ua
        if extra:
            h.update(extra)
        return h

    def _pick_proxy(self) -> str | None:
        """Return the current proxy URL (round-robin advances)."""
        return self.proxy_pool.get()

    @property
    def proxy_url(self) -> str | None:
        """The currently-active proxy URL (read-only).

        Returned value is updated each time :meth:`_pick_proxy` is
        called (i.e. once per crawl or once per explicit
        ``rotate_proxy()`` call).
        """
        return self._active_proxy

    async def _jitter_sleep(self) -> None:
        delay = random.uniform(self.jitter_min, self.jitter_max)
        await asyncio.sleep(delay)

    async def _backoff_sleep(self, attempt: int) -> None:
        delay = min(self.backoff_cap, self.backoff_base * (2**attempt))
        delay = max(0.0, delay + random.uniform(-0.1, 0.1))  # small variance
        await asyncio.sleep(delay)

    # ------------------------------------------------------------------
    # HTTP fetching
    # ------------------------------------------------------------------
    async def fetch(self, url: str, **kwargs: Any) -> _Response:
        """Fetch a URL with rate-limit + retry + proxy + jitter applied.

        Returns a :class:`_Response` wrapper on success. Raises the
        last exception on permanent failure.
        """
        await self._get_rate_limiter().acquire()
        client = self._ensure_client()
        # Single jitter sleep between fetch invocations so we never
        # fire two consecutive requests at the wire simultaneously.
        await self._jitter_sleep()

        # Pop our extra kwargs that are conceptually part of the fetch
        # protocol rather than httpx internals.
        extra_headers = kwargs.pop("headers", None)

        # httpx 0.28 binds proxies at client construction; we rotate
        # proxies by swapping the underlying transport when a new one
        # is needed. For most crawlers the round-robin index will be
        # advanced at most once across a whole batch.
        proxy_url = self._pick_proxy()
        if proxy_url and proxy_url != self._active_proxy:
            self._active_proxy = proxy_url
            self._swap_proxy_client(proxy_url)

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            headers = self._build_headers(extra_headers)
            start = time.monotonic()
            try:
                resp = await client.get(
                    url,
                    headers=headers,
                    **kwargs,
                )
                latency_ms = (time.monotonic() - start) * 1000.0
                content = resp.content
                status = resp.status_code

                if status == httpx.codes.TOO_MANY_REQUESTS:
                    self._stats.record_blocked(bytes=len(content), latency_ms=latency_ms)
                    await self._backoff_sleep(attempt)
                    last_exc = httpx.HTTPStatusError(
                        "429 too many", request=resp.request, response=resp
                    )
                    continue

                if status in (401, 403):
                    # Authentication / anti-bot block — treat as blocked.
                    self._stats.record_blocked(bytes=len(content), latency_ms=latency_ms)
                    await self._backoff_sleep(attempt)
                    last_exc = httpx.HTTPStatusError(
                        f"{status} blocked", request=resp.request, response=resp
                    )
                    continue

                if status >= 500:
                    self._stats.record_failed(bytes=len(content), latency_ms=latency_ms)
                    await self._backoff_sleep(attempt)
                    last_exc = httpx.HTTPStatusError(
                        f"server {status}", request=resp.request, response=resp
                    )
                    continue

                if status >= 400:
                    # 4xx other than 401/403/429: client error, give up.
                    self._stats.record_failed(bytes=len(content), latency_ms=latency_ms)
                    resp.raise_for_status()

                self._stats.record_success(bytes=len(content), latency_ms=latency_ms)
                return _Response(
                    url=str(resp.url),
                    text=resp.text,
                    content=content,
                    status_code=status,
                    headers={k: v for k, v in resp.headers.items()},
                )

            except httpx.TimeoutException as exc:
                latency_ms = (time.monotonic() - start) * 1000.0
                self._stats.record_timeout(latency_ms=latency_ms)
                await self._backoff_sleep(attempt)
                last_exc = exc
            except httpx.HTTPError as exc:
                latency_ms = (time.monotonic() - start) * 1000.0
                self._stats.record_failed(latency_ms=latency_ms)
                await self._backoff_sleep(attempt)
                last_exc = exc

        assert last_exc is not None
        raise last_exc

    async def fetch_html(self, url: str, **kwargs: Any) -> str:
        """Fetch and return the body text directly."""
        resp = await self.fetch(url, **kwargs)
        return resp.text

    async def fetch_bytes(self, url: str, **kwargs: Any) -> bytes:
        """Fetch and return raw bytes."""
        resp = await self.fetch(url, **kwargs)
        return resp.content

    # ------------------------------------------------------------------
    # High-level crawl entrypoint used by orchestrators
    # ------------------------------------------------------------------
    async def crawl(self, url: str, **kwargs: Any) -> list[RawArticle]:
        """Fetch ``url`` and return the parsed articles."""
        response = await self.fetch(url, **kwargs)
        try:
            return await self.parse(response)
        except Exception:
            logger.exception(
                "parse() raised for source=%s url=%s", self.source_name, url
            )
            raise

    # ------------------------------------------------------------------
    # Browser fallback (no-op unless ``use_browser=True``)
    # ------------------------------------------------------------------
    async def fetch_via_browser(self, url: str, **kwargs: Any) -> _Response:
        """Fetch ``url`` via Playwright when ``use_browser=True``.

        Imports :mod:`app.services.news.crawler.browser` lazily so
        the dependency stays optional.
        """
        from app.services.news.crawler.browser import BrowserPool

        await self._get_rate_limiter().acquire()
        await self._jitter_sleep()
        async with BrowserPool() as pool:
            if not pool.is_available():
                # Graceful degradation — same rate limit / retry
                # semantics, just over httpx.
                logger.warning(
                    "Browser requested but unavailable for source=%s; "
                    "falling back to httpx",
                    self.source_name,
                )
                return await self.fetch(url, **kwargs)
            page = await pool.new_page()
            try:
                start = time.monotonic()
                await page.goto(url, wait_until="domcontentloaded")
                content = await page.content()
                latency_ms = (time.monotonic() - start) * 1000.0
                self._stats.record_success(bytes=len(content), latency_ms=latency_ms)
                return _Response(
                    url=url,
                    text=content,
                    content=content.encode("utf-8", "ignore"),
                    status_code=200,
                    headers={},
                )
            finally:
                await pool.release(page)

    # ------------------------------------------------------------------
    # Helpers subclasses can reuse
    # ------------------------------------------------------------------
    @staticmethod
    def strip_html(text: str) -> str:
        """Drop HTML tags / entities so output is plain text."""
        if not text:
            return ""
        no_tags = re.sub(r"<[^>]+>", "", text)
        return re.sub(r"\s+", " ", no_tags).strip()

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "BaseCrawler must be entered via 'async with' before fetch(); "
                "alternatively, pass client=... at construction."
            )
        return self._client

    def _swap_proxy_client(self, proxy_url: str) -> None:
        """Recreate the underlying client with a new proxy URL.

        httpx 0.28 binds proxies at client construction; the cheapest
        way to "rotate" at runtime is therefore to create a sibling
        client and swap it in. We only do this when the proxy URL
        actually changes, so steady-state crawls pay nothing.
        """
        if self._client is not None and not self._owns_client:
            # The caller owns this client — we can't safely swap it
            # out from under them. Proxy rotation is therefore a no-op
            # in this mode.
            return
        new_client = httpx.AsyncClient(
            proxy=proxy_url,
            timeout=httpx.Timeout(self.request_timeout),
            follow_redirects=True,
            headers=dict(DEFAULT_HEADERS),
            trust_env=True,
        )
        # The previously-built one (if any) will be closed in
        # ``__aexit__``; we don't close it eagerly because we may still
        # have in-flight requests on it. httpx.AsyncClient instances
        # are independently awaitable.
        self._client = new_client
        self._owns_client = True

    # ------------------------------------------------------------------
    # To be implemented by subclasses
    # ------------------------------------------------------------------
    @abstractmethod
    async def parse(self, response: _Response) -> list[RawArticle]:
        """Parse a response into a list of articles.

        Implementations should treat this as the only thing they
        need to write — every other concern (UA, rate limit, retries,
        proxies, stats) is handled by the base.
        """
        raise NotImplementedError
