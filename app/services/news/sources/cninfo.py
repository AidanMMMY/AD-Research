"""巨潮资讯 (cninfo) public-disclosure crawler.

Cninfo is the official disclosure portal for the Shenzhen Stock
Exchange and also carries Shanghai Stock Exchange filings since the
2020 consolidation. A-share listed companies file annual reports,
quarterly reports, tender offers, related-party-transaction
announcements, etc. here.

Endpoint
--------
POST  http://www.cninfo.com.cn/new/hisAnnouncement/query
Form body:
  pageNum, pageSize, column=szse / sse, tabName=fulltext,
  stock, plate=sh / sz, category=category_ndbg_szsh; ...

We keep the implementation small: one request per ``category`` we care
about, two pages per category, no per-stock filtering (the server
returns a cross-section of recent filings which is plenty for a
daily news feed).

Rate limit
----------
Self-imposed 20 req/min via :attr:`rate_limit_per_min`. Cninfo's
public API is undocumented but responds to normal polling. Higher
rates trip the WAF.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from app.services.news.crawler.base import BaseCrawler, _Response
from app.services.news.crawler.types import RawArticle

logger = logging.getLogger(__name__)

CNINFO_QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_DETAIL_URL = "http://www.cninfo.com.cn/new/disclosure/detail"

# We cover the four most-common filing categories. Each is a separate
# paginated query. Tune ``PAGE_SIZE`` if you need deeper history.
DEFAULT_CATEGORIES: tuple[str, ...] = (
    "category_ndbg_szsh",   # 年度报告 (Annual report)
    "category_yjdbg_szsh",  # 一季度报告 (Q1 report)
    "category_sjdbg_szsh",  # 三季度报告 (Q3 report)
    "category_bndbg_szsh",  # 半年度报告 (Interim report)
)
PAGE_SIZE = 30

# Extra headers cninfo expects on POST (overrides the base UA/Referer).
CNINFO_EXTRA_HEADERS: dict[str, str] = {
    "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
    "Origin": "http://www.cninfo.com.cn",
    "X-Requested-With": "XMLHttpRequest",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept": "application/json, text/plain, */*",
}


class CninfoCrawler(BaseCrawler):
    """Crawl A-share company filings from 巨潮资讯."""

    source_name = "cninfo"
    rate_limit_per_min = 20
    request_timeout = 20.0
    market = "cn_a"
    language = "zh"

    def __init__(
        self,
        *,
        categories: tuple[str, ...] = DEFAULT_CATEGORIES,
        page_size: int = PAGE_SIZE,
        **kwargs,  # forwarded to BaseCrawler
    ) -> None:
        kwargs.setdefault("rate_limit_per_min", self.rate_limit_per_min)
        super().__init__(**kwargs)
        self._categories = categories
        self._page_size = page_size

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def crawl(self, *, page_num: int = 1) -> list[RawArticle]:
        """POST one page of filings for every configured category."""
        out: list[RawArticle] = []
        for cat in self._categories:
            try:
                arts = await self._fetch_one(category=cat, page_num=page_num)
                out.extend(arts)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Cninfo fetch failed for %s: %s", cat, exc)
                continue
        return out

    async def _fetch_one(self, *, category: str, page_num: int) -> list[RawArticle]:
        """One POST against the disclosure query endpoint."""
        form = {
            "pageNum": str(page_num),
            "pageSize": str(self._page_size),
            "column": "szse",
            "tabName": "fulltext",
            "plate": "",
            "stock": "",
            "searchkey": "",
            "secid": "",
            "category": category,
            "trade": "",
            "seDate": "",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        # ``self.client`` is the BaseCrawler's httpx client. We hand-roll
        # the POST (rather than going through ``self.fetch`` which is
        # GET-only) so we can pass form-encoded data + custom headers.
        client = self._ensure_client()
        await self._get_rate_limiter().acquire()
        await self._jitter_sleep()
        # Use the base helper for stats / retries is tempting but the
        # existing helper is GET-only; keep this simple and re-use the
        # retry/backoff primitives by hand.
        from app.services.news.crawler.base import _Response  # noqa: F401

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = await client.post(
                    CNINFO_QUERY_URL,
                    data=form,
                    headers={**self._build_headers(), **CNINFO_EXTRA_HEADERS},
                )
                self._stats.record_success(bytes=len(resp.content))
                return self._parse_payload(resp.json())
            except Exception as exc:  # noqa: BLE001
                self._stats.record_failed()
                last_exc = exc
                await self._backoff_sleep(attempt)
        assert last_exc is not None
        raise last_exc

    def _parse_payload(self, payload) -> list[RawArticle]:
        if not isinstance(payload, dict):
            return []
        announcements = payload.get("announcements") or []
        if not isinstance(announcements, list):
            return []
        out: list[RawArticle] = []
        for item in announcements:
            if not isinstance(item, dict):
                continue
            title = (item.get("announcementTitle") or "").strip()
            # Cninfo title carries an HTML ``<em>...`` highlight wrapper
            # when the search matched against a keyword — strip it.
            title = _strip_html_inline(title)
            adj_url = (item.get("adjunctUrl") or "").strip()
            if not title or not adj_url:
                continue
            # Cninfo's adjunctUrl is a path under static.cninfo.com.cn.
            url = f"http://static.cninfo.com.cn/{adj_url.lstrip('/')}"
            ann_time_ms = item.get("announcementTime")
            published_at = _ms_to_dt(ann_time_ms) or datetime.now(tz=timezone.utc)
            stock_code = (item.get("secCode") or "").strip()
            stock_name = (item.get("secName") or "").strip()
            ann_id = item.get("announcementId")
            # ``announcementId`` may be an int (cninfo's common case) or
            # a stringified form. Normalize to str for the source_id
            # column and fall back to the URL on missing.
            if ann_id is None or ann_id == "":
                source_id = adj_url
            else:
                source_id = str(ann_id)

            art = RawArticle(
                source=self.source_name,
                source_id=str(source_id) if source_id else adj_url,
                url=url,
                title=title,
                published_at=published_at,
                body=None,
                body_html=None,
                author=None,
                language=self.language,
                market=self.market,
                extra={
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "category": item.get("category"),
                    "announcement_id": source_id,
                },
            )
            out.append(art)
        return out

    # Backwards-compat with the spec: ``parse(response)`` accepts a
    # dict (or a ``_Response`` whose ``.text`` parses to JSON).
    async def parse(self, response) -> list[RawArticle]:  # type: ignore[override]
        if isinstance(response, dict):
            return self._parse_payload(response)
        if isinstance(response, _Response):
            try:
                import json as _json
                return self._parse_payload(_json.loads(response.text))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Cninfo parse JSON error: %s", exc)
                return []
        return []

    async def run(self, db) -> int:
        """Fetch, normalize, and persist. Returns inserted row count."""
        from app.services.news.normalizer import NewsNormalizer

        raw_articles = await self.crawl()
        if not raw_articles:
            return 0
        normalizer = NewsNormalizer(db)
        inserted = 0
        for raw in raw_articles:
            try:
                article = normalizer.normalize(raw)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Cninfo normalize failed: %s", exc)
                continue
            if article is not None:
                inserted += 1
        db.commit()
        return inserted


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html_inline(value: str) -> str:
    if not value:
        return ""
    return _HTML_TAG_RE.sub("", value).strip()


def _ms_to_dt(value) -> datetime | None:
    """Convert a millisecond Unix timestamp (cninfo's ``announcementTime``)
    to a UTC-aware :class:`datetime`. Returns ``None`` for invalid input.
    """
    if value is None:
        return None
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    seconds = ms / 1000.0
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
