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


@lru_cache(maxsize=64)
def _robots_parser(robots_url: str) -> RobotFileParser:
    """Return a cached RobotFileParser for the given robots.txt URL.

    The parser is read lazily by :func:`is_robots_allowed`; this cache only
    stores the empty parser instance so we don't re-parse the same URL many
    times inside a single process.
    """
    rp = RobotFileParser()
    rp.set_url(robots_url)
    return rp


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
        # RobotFileParser.read() performs a blocking HTTP request; push it to
        # a thread so we don't stall the event loop.
        await asyncio.to_thread(rp.read)
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
