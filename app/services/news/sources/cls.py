"""财联社 (CLS) telegraph JSON API crawler.

Endpoint
--------
``https://www.cls.cn/api/cache?name=telegraph&rn=20`` — public JSON API
backing the 财联社电报 rolling feed.

Response shape::

    {
      "errno": 0,
      "data": {
        "roll_data": [
          {
            "id": 2433191,
            "type": -1,
            "title": "...",
            "brief": "...",
            "content": "...",
            "ctime": "1753xxx"   // unix seconds, string
          }
        ]
      }
    }

Anti-bot notes
--------------
The site sits behind CloudWAF: the default ``requests`` TLS fingerprint
is blocked, but plain httpx with a desktop Chrome User-Agent currently
works. Defensive behaviour: a non-JSON (WAF HTML) response or a non-zero
``errno`` yields an empty list plus a warning — never an exception — so
the scheduler tick records a quiet failure instead of crashing.

Rate limit
----------
20 req/min self-imposed.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.services.news.crawler.base import BaseCrawler, _Response
from app.services.news.crawler.robots import is_robots_allowed
from app.services.news.crawler.types import RawArticle

logger = logging.getLogger(__name__)

CLS_TELEGRAPH_URL = "https://www.cls.cn/api/cache?name=telegraph&rn=20"
CLS_DETAIL_URL = "https://www.cls.cn/detail/{id}"

# A stable desktop Chrome UA — CloudWAF fingerprints anything that looks
# like a script. The base UA pool is fine too, but pinning one keeps the
# request profile consistent across retries.
_DESKTOP_CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class ClsCrawler(BaseCrawler):
    """Crawl the CLS telegraph JSON API."""

    source_name = "cls"
    rate_limit_per_min = 20
    market = "cn_a"
    language = "zh"

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("rate_limit_per_min", self.rate_limit_per_min)
        super().__init__(**kwargs)

    async def crawl(self) -> list[RawArticle]:  # type: ignore[override]
        if not await is_robots_allowed(CLS_TELEGRAPH_URL):
            logger.warning("%s blocked by robots.txt", self.source_name)
            return []
        response = await self.fetch(
            CLS_TELEGRAPH_URL,
            headers={
                "User-Agent": _DESKTOP_CHROME_UA,
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.cls.cn/telegraph",
            },
        )
        return await self.parse(response)

    async def parse(self, response: _Response) -> list[RawArticle]:  # type: ignore[override]
        payload = self._parse_json_payload(response.text)
        if payload is None:
            return []
        items = payload.get("data", {}).get("roll_data", []) or []

        out: list[RawArticle] = []
        for item in items:
            article = self._item_to_article(item)
            if article is not None:
                out.append(article)
        return out

    def _parse_json_payload(self, text: str) -> dict[str, Any] | None:
        """Parse the API envelope, guarding against WAF HTML and errno != 0."""
        stripped = (text or "").lstrip()
        if not stripped.startswith("{"):
            logger.warning(
                "%s returned non-JSON response (likely WAF block): %.120s",
                self.source_name,
                stripped,
            )
            return None
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            logger.warning("%s JSON decode failed: %s", self.source_name, exc)
            return None
        if not isinstance(payload, dict):
            logger.warning("%s unexpected payload type", self.source_name)
            return None
        errno = payload.get("errno")
        if errno != 0:
            logger.warning(
                "%s API errno=%s msg=%s",
                self.source_name,
                errno,
                payload.get("msg"),
            )
            return None
        return payload

    def _item_to_article(self, item: dict[str, Any]) -> RawArticle | None:
        item_id = item.get("id")
        if not item_id:
            return None
        url = CLS_DETAIL_URL.format(id=item_id)

        title = (item.get("title") or "").strip()
        brief = self.strip_html(item.get("brief") or "")
        content_html = (item.get("content") or "").strip() or None
        content_text = self.strip_html(item.get("content") or "")
        if not title:
            # Telegraph flashes often have no headline; fall back to the
            # brief so the normalizer's required-title check passes.
            title = (brief or content_text)[:50].strip()
        if not title:
            return None

        try:
            published_at = datetime.fromtimestamp(int(item.get("ctime", 0)), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            published_at = datetime.now(tz=timezone.utc)

        return RawArticle(
            source=self.source_name,
            source_id=str(item_id),
            url=url,
            title=title,
            body=content_text or brief or None,
            body_html=content_html,
            author="财联社",
            published_at=published_at,
            language=self.language,
            market=self.market,
            extra={"cls_type": item.get("type")},
        )
