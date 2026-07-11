"""Cninfo (巨潮资讯) public announcement provider.

Public, key-free endpoint used by A-share periodic report ingestion:

    POST http://www.cninfo.com.cn/new/hisAnnouncement/query

It is the same endpoint that cninfo.com.cn's own announcement-list page
calls.  We hit it with form-encoded body parameters; the response is
JSON containing an ``announcements`` array (or ``announcement`` depending
on the upstream version) — each item carries the upstream
``announcementId``, ``announcementTitle``, ``adjunctUrl`` and a few other
metadata fields.

As of 2026 the upstream filter behaviour changed: passing
``stock=<orgId>`` together with a ``category_*_szsh`` filter now returns
an empty array, but ``stock=""`` + ``secid=<orgId>`` still works for
every exchange (SH / SZ / BSE).  We use the latter form here.  The
``column`` parameter (``sse``/``szse``/``bse``) is now effectively
ignored when ``secid`` is supplied, so we still cycle through all three
for safety against future cninfo changes.

CNINFO rate-limiting is undocumented; in practice the site tolerates a
small burst but will start returning HTTP 503 once you cross ~30 req/min.
We sleep ~2s between calls and retry once on 429/503.

The provider is best-effort: every public method returns ``list[dict]``
and is expected to swallow transient failures and return an empty list
rather than raise.
"""

import json
import logging
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

_BASE_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept": "*/*",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "http://www.cninfo.com.cn",
    "Referer": "http://www.cninfo.com.cn/new/disclosure/stock?stockCode=&orgId=",
}

_REQUEST_TIMEOUT = 15

# Best-effort polite pacing — keep CNINFO within ~30 req/min.
_MIN_INTERVAL = 2.0

# Upstream ``seDate`` silently returns empty when the span exceeds roughly
# two years.  We split wide ranges into 2-year slices and merge the results.
_MAX_DATE_SLICE_YEARS = 2


def _date_slices(start_date: date, end_date: date, max_years: int = _MAX_DATE_SLICE_YEARS):
    """Yield (slice_start, slice_end) date pairs covering [start_date, end_date]."""
    slice_start = start_date
    while slice_start <= end_date:
        slice_end = min(
            end_date,
            slice_start.replace(year=slice_start.year + max_years),
        )
        # ``replace(year=...)`` can overflow for leap-day; clamp to month-end.
        if slice_end.year != slice_start.year + max_years:
            # Reached the upper bound already, no need to adjust.
            pass
        elif slice_end.month == 2 and slice_end.day == 29:
            slice_end = date(slice_end.year, 2, 28)
        yield slice_start, slice_end
        slice_start = slice_end + timedelta(days=1)


# Mapping from ``period_type`` (our internal code) to the cninfo
# ``category`` parameter.  Note: cninfo uses the same ``category_*`` codes
# for SZSE / SSE / BSE; we collapse all three into the SZSH variant which
# works across exchanges in practice.
_PERIOD_TO_CATEGORY = {
    "annual": "category_ndbg_szsh",
    "semi": "category_bndbg_szsh",
    "q1": "category_yjdbg_szsh",
    "q3": "category_sjdbg_szsh",
}


# Reverse mapping from cninfo category → adjunct_type for storage.
_CATEGORY_TO_ADJUNCT = {v: k for k, v in _PERIOD_TO_CATEGORY.items()}


class CninfoProvider:
    """Public client for cninfo's ``hisAnnouncement/query`` endpoint."""

    name = "cninfo"

    def __init__(self) -> None:
        # Last-call timestamp used for polite pacing.
        self._last_call = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_org_id(self, ts_code: str) -> str | None:
        """Resolve a Tushare ``ts_code`` (``600519.SH``) to a cninfo ``orgId``.

        Reads the static lookup table at
        ``app/data/static/cninfo_org_ids.json``.  Returns ``None`` when
        the file is missing or the code is not present.
        """
        if not ts_code:
            return None
        path = (
            Path(__file__).parent.parent / "static" / "cninfo_org_ids.json"
        )
        if not path.exists():
            logger.warning("Cninfo org-id table not found at %s", path)
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read cninfo org-id table: %s", exc)
            return None
        return data.get(ts_code)

    def fetch_announcements(
        self,
        org_id: str,
        start_date: date,
        end_date: date,
        period_type: str,
        *,
        page_size: int = 30,
        max_pages: int = 5,
    ) -> list[dict[str, Any]]:
        """Fetch periodic announcements for one ``org_id``.

        Args:
            org_id: Cninfo orgId (e.g. ``gssh0600519``).
            start_date: inclusive lower bound on announcement date.
            end_date: inclusive upper bound on announcement date.
            period_type: ``"annual"``, ``"semi"``, ``"q1"`` or ``"q3"``.
            page_size: items per page (default 30, max ~30 upstream).
            max_pages: hard cap on pagination depth.

        Returns:
            A list of normalised dicts with keys that map directly to the
            :class:`CninfoReport` ORM (with a few extras preserved in
            ``raw_payload``).
        """
        category = _PERIOD_TO_CATEGORY.get(period_type)
        if not category:
            logger.warning("Unknown period_type %s for cninfo", period_type)
            return []

        out: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for slice_start, slice_end in _date_slices(start_date, end_date):
            se_date = f"{slice_start.isoformat()}~{slice_end.isoformat()}"
            page_num = 1
            while page_num <= max_pages:
                # cninfo's ``stock=<orgId>`` + category_*_szsh combo now
                # returns 0 results; using ``secid=<orgId>`` with empty
                # ``stock`` still works and is exchange-agnostic.  The
                # ``column`` parameter is ignored when ``secid`` is supplied,
                # so a single request per page is sufficient.
                payload = {
                    "stock": "",
                    "tabName": "fulltext",
                    "pageSize": str(page_size),
                    "pageNum": str(page_num),
                    "column": "szse",
                    "category": category,
                    "plate": "",
                    "seDate": se_date,
                    "searchkey": "",
                    "secid": org_id,
                    "sortName": "",
                    "sortType": "",
                    "isHLtitle": "true",
                }
                body = self._post_form(payload)
                if not body:
                    break

                announcements = body.get("announcements") or body.get(
                    "announcement"
                ) or []
                if not announcements:
                    break

                for ann in announcements:
                    normalised = _normalise_announcement(ann, org_id, period_type)
                    if normalised:
                        ann_id = str(normalised.get("announcement_id") or "")
                        if ann_id and ann_id in seen_ids:
                            continue
                        if ann_id:
                            seen_ids.add(ann_id)
                        out.append(normalised)

                # Stop when we got fewer than a full page — no more data.
                if len(announcements) < page_size:
                    break
                page_num += 1

        return out

    def fetch_periodic_reports(
        self,
        org_id: str,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Fetch all four periodic report types in one call.

        Convenience wrapper that runs the four upstream ``category_*``
        queries sequentially and concatenates the results.  The
        adjunct_type of each returned record is set accordingly so the
        caller can upsert without further work.
        """
        out: list[dict[str, Any]] = []
        for period in ("annual", "semi", "q1", "q3"):
            try:
                out.extend(
                    self.fetch_announcements(
                        org_id=org_id,
                        start_date=start_date,
                        end_date=end_date,
                        period_type=period,
                    )
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "cninfo %s fetch failed for %s: %s", period, org_id, exc
                )
        return out

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _post_form(self, payload: dict[str, str]) -> dict[str, Any] | None:
        """POST form-encoded ``payload`` and return parsed JSON or None.

        Best-effort: a transient failure returns ``None`` rather than
        raising, so callers can decide whether to retry / continue.
        """
        self._pace()

        try:
            resp = requests.post(
                _BASE_URL,
                headers=_HEADERS,
                data=payload,
                timeout=_REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.warning("cninfo POST failed: %s", exc)
            return None

        # Rate-limit / transient — sleep once and retry, then give up.
        if resp.status_code in (429, 503):
            logger.warning(
                "cninfo HTTP %s — sleeping 5s and retrying once", resp.status_code
            )
            time.sleep(5)
            try:
                resp = requests.post(
                    _BASE_URL,
                    headers=_HEADERS,
                    data=payload,
                    timeout=_REQUEST_TIMEOUT,
                )
            except requests.RequestException as exc:
                logger.warning("cninfo retry failed: %s", exc)
                return None

        if resp.status_code != 200:
            logger.warning(
                "cninfo HTTP %s body=%s",
                resp.status_code,
                resp.text[:200] if resp.text else "",
            )
            return None

        try:
            return resp.json()
        except ValueError as exc:
            logger.warning("cninfo response was not valid JSON: %s", exc)
            return None

    def _pace(self) -> None:
        """Sleep just enough to keep us below ~30 req/min."""
        elapsed = time.time() - self._last_call
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        self._last_call = time.time()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _normalise_announcement(
    ann: dict[str, Any],
    org_id: str,
    period_type: str,
) -> dict[str, Any] | None:
    """Map a single upstream record to the keys on ``CninfoReport``."""
    announcement_id = (
        ann.get("announcementId")
        or ann.get("announcement_id")
        or ann.get("id")
    )
    if announcement_id is None:
        return None
    announcement_id = str(announcement_id)

    title = ann.get("announcementTitle") or ann.get("announcement_title") or ""
    adjunct_url = ann.get("adjunctUrl") or ann.get("adjunct_url") or ""

    announcement_time = ann.get("announcementTime") or ann.get(
        "announcement_time"
    )
    if not announcement_time:
        return None

    sec_code = ann.get("secCode") or ann.get("sec_code")
    stock_code = str(sec_code) if sec_code else ""

    return {
        "announcement_id": announcement_id,
        "announcement_title": str(title),
        "adjunct_url": str(adjunct_url),
        "announcement_time": announcement_time,
        "org_id": org_id,
        "sec_code": sec_code,
        "stock_code": stock_code,
        "adjunct_type": period_type,
        "is_periodic": True,
        "fiscal_quarter": {
            "annual": 4,
            "semi": 2,
            "q1": 1,
            "q3": 3,
        }.get(period_type),
        "raw_payload": ann,
    }