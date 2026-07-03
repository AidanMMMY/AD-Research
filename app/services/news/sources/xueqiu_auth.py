"""Xueqiu authentication / cookie handling.

Xueqiu's mobile-style JSON endpoints are open to logged-out callers, but
rate-limit aggressively. A valid ``xq_a_token`` cookie raises the limit
substantially and unlocks higher-resolution feeds.

We never attempt to *log in* programmatically (no password, plus a real
risk of tripping account security). Instead, the operator must paste the
raw ``Cookie`` header value from a browser session into the
``XUEQIU_COOKIE`` environment variable. The auth layer is responsible for:

* Parsing the string into a usable ``httpx.Cookies`` object.
* Detecting obviously-stale cookies (expired ``xq_a_token`` or empty
  payload) without making any network call.
* Performing a lightweight live probe (one GET against the public
  timeline) so the caller can show a clear error when the cookie has been
  invalidated.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from dataclasses import dataclass, field
from typing import Iterable

import httpx

from app.services.news.crawler.base import DEFAULT_HEADERS, DEFAULT_USER_AGENTS, make_client

logger = logging.getLogger(__name__)


XUEQIU_BASE_URL = "https://xueqiu.com"

# Default probe endpoint — a single-post public feed. Cheap and present
# even when the search API rejects our cookie.
_PROBE_URL = f"{XUEQIU_BASE_URL}/v4/statuses/public_timeline.json"
_PROBE_PARAMS = {"count": 1, "max_id": -1, "symbol": "SH000300"}


class XueqiuAuthError(RuntimeError):
    """Raised when the Xueqiu cookie is missing, malformed, or rejected."""


@dataclass
class XueqiuAuth:
    """Cookie-driven Xueqiu auth.

    Construct with no arguments in production code: the cookie string is
    read from the ``XUEQIU_COOKIE`` env var (or the ``xueqiu_cookie``
    field in ``Settings``). Tests can pass an explicit ``cookie`` string.
    """

    cookie: str = ""
    # Cache for the parsed cookies so we don't reparse on every request.
    _cookies: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _probed_at: float = 0.0
    _probe_ok: bool | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.cookie:
            self.cookie = os.getenv("XUEQIU_COOKIE", "")
        self._cookies = _parse_cookie_string(self.cookie)
        # Validate immediately so callers get a fast error rather than
        # discovering a missing token at first network call.
        _require_token(self._cookies)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def has_cookie(self) -> bool:
        return bool(self._cookies.get("xq_a_token"))

    @property
    def cookie_header(self) -> str:
        """Return the original cookie string (for direct ``Cookie:`` injection)."""
        return self.cookie

    def as_httpx_cookies(self) -> httpx.Cookies:
        return httpx.Cookies(self._cookies)

    async def is_valid(self, *, force: bool = False) -> bool:
        """Probe the public timeline to verify the cookie is accepted.

        Cached for 5 minutes to avoid burning rate limit on every call.
        Returns False on any HTTP error, JSON parse failure, or an
        empty/non-OK response body. Never raises — callers should treat
        ``False`` as "the cookie needs refreshing".
        """
        if not force and self._probe_ok is not None and (time.time() - self._probed_at) < 300:
            return self._probe_ok

        try:
            headers = dict(DEFAULT_HEADERS)
            headers["User-Agent"] = random.choice(DEFAULT_USER_AGENTS)
            async with make_client(headers=headers) as client:
                resp = await client.get(
                    _PROBE_URL,
                    params=_PROBE_PARAMS,
                    cookies=self._cookies,
                )
        except (httpx.HTTPError, asyncio.TimeoutError) as exc:
            logger.warning("Xueqiu auth probe network error: %s", exc)
            self._probe_ok = False
            self._probed_at = time.time()
            return False

        ok = resp.status_code == 200
        if ok:
            try:
                payload = resp.json()
            except ValueError:
                ok = False
            else:
                # Xueqiu sometimes returns 200 with an HTML login page or a
                # {"error_*": ...} envelope when the cookie is stale.
                if not isinstance(payload, dict) or "list" not in payload:
                    ok = False
                elif payload.get("error_code") not in (None, "0", 0):
                    ok = False

        self._probe_ok = ok
        self._probed_at = time.time()
        if not ok:
            logger.warning(
                "Xueqiu cookie rejected (status=%s, body[:120]=%r)",
                resp.status_code,
                resp.text[:120],
            )
        return ok

    async def wait_until_valid(
        self,
        *,
        attempts: int = 3,
        backoff_seconds: float = 60.0,
    ) -> bool:
        """Try ``is_valid`` repeatedly with a long backoff.

        Used by the scheduler when a fetch batch fails because the cookie
        was rotated upstream — we sleep, retry, and only skip the run if
        the cookie is still rejected. Returns True on success, False on
        permanent failure.
        """
        for i in range(attempts):
            if await self.is_valid(force=True):
                return True
            if i < attempts - 1:
                logger.info(
                    "Xueqiu cookie still invalid, sleeping %.0fs before retry %d/%d",
                    backoff_seconds, i + 2, attempts,
                )
                await asyncio.sleep(backoff_seconds)
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_cookie_string(raw: str) -> dict[str, str]:
    """Parse a ``Cookie:`` header value or a free-form cookie string.

    Accepts both formats::

        "xq_a_token=abc; u=12345; device_id=xyz"
        "xq_a_token=abc; u=12345"

    Whitespace around entries is tolerated; duplicate keys keep the last
    occurrence (matches browser behaviour).
    """
    if not raw:
        return {}

    out: dict[str, str] = {}
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        key, _, value = chunk.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        out[key] = value
    return out


def _require_token(cookies: dict[str, str]) -> None:
    """Raise if the token is obviously unusable."""
    if not cookies:
        raise XueqiuAuthError(
            "XUEQIU_COOKIE is not set. Paste a logged-in browser Cookie "
            "header into the XUEQIU_COOKIE env var (must include "
            "xq_a_token=...; u=...; device_id=...)."
        )
    token = cookies.get("xq_a_token", "")
    if not token or len(token) < 8:
        raise XueqiuAuthError(
            "Xueqiu cookie is missing or has an empty xq_a_token. "
            "Refresh the value of XUEQIU_COOKIE."
        )


def merge_with_default_headers(extra: Iterable[tuple[str, str]] | None = None) -> dict[str, str]:
    """Return the default browser headers, optionally extended."""
    headers = dict(DEFAULT_HEADERS)
    if extra:
        for k, v in extra:
            headers[k] = v
    return headers
