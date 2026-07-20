"""Lightweight robots.txt checker for news crawlers.

The framework previously had no robots.txt handling. This helper gives
new crawlers a best-effort way to check and log compliance status without
blocking the scheduler when a site has no robots.txt.
"""

from __future__ import annotations

import asyncio
import logging
import urllib.parse
from functools import lru_cache
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)

# Hard cap on the robots.txt fetch. ``RobotFileParser.read()`` uses urllib
# with *no* timeout — a single dropped connection (common when WAFs filter
# cloud IPs) would wedge the calling scheduler job forever.
_ROBOTS_FETCH_TIMEOUT = 10.0

# A browser-ish UA: several sites (WAFs) 403 the default Python-urllib UA,
# and robotparser treats 403 as "disallow everything", which would silently
# zero out every crawl.
_ROBOTS_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@lru_cache(maxsize=64)
def _robots_parser(robots_url: str) -> RobotFileParser:
    """Return a cached RobotFileParser for the given robots.txt URL.

    The cache only stores the parser instance; the robots.txt body is
    re-fetched and re-parsed on every check so rule changes are picked up
    without a process restart.
    """
    rp = RobotFileParser()
    rp.set_url(robots_url)
    return rp


def _fetch_robots(robots_url: str) -> str | None:
    """Fetch a robots.txt body with an explicit timeout.

    Returns ``None`` when the file is missing or unreachable — the caller
    treats that as "no rules", matching the documented best-effort policy.
    """
    import httpx

    try:
        resp = httpx.get(
            robots_url,
            headers={"User-Agent": _ROBOTS_UA},
            timeout=_ROBOTS_FETCH_TIMEOUT,
            follow_redirects=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("robots.txt fetch failed for %s: %s", robots_url, exc)
        return None
    if resp.status_code != 200:
        logger.debug(
            "robots.txt for %s returned HTTP %d; assuming allowed",
            robots_url,
            resp.status_code,
        )
        return None
    return resp.text


async def is_robots_allowed(url: str, user_agent: str = "*") -> bool:
    """Check whether ``url`` is allowed by the site's robots.txt.

    Returns ``True`` when:
      - the site has no robots.txt (404 / unreachable), or
      - robots.txt explicitly allows the path.

    Returns ``False`` only when the robots.txt is reachable and explicitly
    disallows the path. The result is logged either way so operators can
    audit crawler compliance.
    """
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        logger.debug("robots check skipped for malformed url: %s", url)
        return True

    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        rp = _robots_parser(robots_url)
        # The blocking HTTP fetch is pushed to a thread so we don't stall
        # the event loop; it is hard-capped by _ROBOTS_FETCH_TIMEOUT.
        body = await asyncio.to_thread(_fetch_robots, robots_url)
        if body is None:
            return True
        rp.parse(body.splitlines())
        allowed = rp.can_fetch(user_agent, url)
        if allowed:
            logger.debug("robots allowed: %s", url)
        else:
            logger.warning("robots DISALLOWED: %s (robots.txt: %s)", url, robots_url)
        return allowed
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "robots.txt fetch/parsing failed for %s: %s; assuming allowed",
            robots_url,
            exc,
        )
        return True
