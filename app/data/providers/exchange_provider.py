"""交易所官方披露页 → PDF 直链解析。

支持 SSE / SZSE / BSE。统一接口：给定 ts_code + 日期范围，
返回可能的 PDF URL 列表（按时间倒序）。

实现说明：
- SSE 的 listing API ``queryCompanyBulletinNew.do`` 返回 JSON，
  PDF 链接在 ``URL`` 字段（相对路径如 ``/disclosure/listedinfo/
  announcement/c/new/2026-06-22/600519_20260622_ZTRO.pdf``）。
- SZSE 的 listing API ``/api/disc/announcement/annList`` 返回
  JSON，PDF 链接在 ``attachPath`` 字段（相对路径）。
- BSE 的 API 在我们这边被 WAF 阻断 — 本版本对 BSE 返回 None。

PDF 实际下载：
- SZSE 直接从 ``disc.static.szse.cn`` 拿 PDF，无需 JS；
- SSE 的 ``static.sse.com.cn`` 有 ``acw_sc__v2`` 反爬挑战，
  无浏览器自动化时只能拿到 JS 质询页（HTML）。我们把质询
  视为 fail，并记录日志，方便后续接 acw_sc_v2 solver。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any

import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public constants — also re-used by ``CninfoReportService`` for the
# Provider builder to construct files / labels etc.
# ---------------------------------------------------------------------------


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


# Endpoints
_SSE_LIST_URL = "https://query.sse.com.cn/security/stock/queryCompanyBulletinNew.do"
_SSE_STATIC_BASE = "https://static.sse.com.cn"

_SZSE_LIST_URL = "http://www.szse.cn/api/disc/announcement/annList"
_SZSE_STATIC_BASE = "http://disc.static.szse.cn"

# BSE's CDN appears to block our network tier (302 challenge). Left
# as a stub so callers know the provider exists for BSE even when
# we cannot currently resolve any URL.
_BSE_LIST_URL = "https://www.bse.cn/notice/announcement.html"


# Network params
_REQUEST_TIMEOUT = 15


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _exchange_for_code(stock_code: str) -> str | None:
    """Return ``"SSE"`` / ``"SZSE"`` / ``"BSE"`` for a 6-digit A-share code.

    Mirrors the logic in ``app.data.disclosure_routes._exchange_for`` so
    the provider and the seeder agree on the routing rule.
    """
    code = stock_code
    if len(code) > 6:
        code = code[:6]
    if not code:
        return None
    if code.startswith(("60", "68")):
        return "SSE"
    if code.startswith(("00", "30")):
        return "SZSE"
    if code.startswith(("83", "87", "88", "92", "43", "4")):
        return "BSE"
    return None


def _strip_ts_suffix(ts_code: str) -> str:
    """``600519.SH`` → ``600519``."""
    return ts_code.split(".")[0] if ts_code else ""


def _levenshtein(a: str, b: str) -> int:
    """Compact Levenshtein distance for short hint matches.

    Standard DP, bounded on the smaller string length so we don't
    blow up on long titles.  Not optimised — used for ranking at
    most ~50 candidates per call.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) > len(b):
        a, b = b, a
    n, m = len(a), len(b)
    prev = list(range(n + 1))
    for j in range(1, m + 1):
        cur = [j] + [0] * n
        for i in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[i] = min(cur[i - 1] + 1, prev[i] + 1, prev[i - 1] + cost)
        prev = cur
    return prev[n]


def _score(title: str, hint: str | None) -> tuple[int, int]:
    """Return ``(-score, date)`` — higher score wins, then earlier
    date wins (so the matcher prefers the freshest matching PDF)."""
    base = 0
    if hint:
        # Match against the first 30 chars of the title which carry
        # the report name (e.g. "贵州茅台2025年年度报告").
        head = re.sub(r"\s+", "", title[:30])
        ref = re.sub(r"\s+", "", hint[:30])
        if head and head == ref:
            base += 100
        else:
            d = _levenshtein(head, ref)
            base += max(0, 30 - d)
    return base


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class ExchangeProvider:
    """给定 ``ts_code`` + 日期范围，从 SSE / SZSE / BSE 列表页找出
    可能的 PDF 链接（按时间倒序）。"""

    name = "exchange"

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(_HEADERS)

    # ----- public API ------------------------------------------------

    def find_report_pdf(
        self,
        ts_code: str,
        target_date: date,
        title_hint: str | None = None,
        *,
        tolerance_days: int = 7,
    ) -> str | None:
        """Return a candidate PDF URL or ``None`` if nothing found.

        Tries the exchange that owns ``ts_code`` first; if no candidate
        matches the date + title hint, walks a wider date window
        (``tolerance_days`` each side) so we don't miss reports that
        were published a day or two before/after ``target_date`` due
        to timezone drift.

        Returns the first (best-scored) URL.  The caller is expected
        to ``requests.get()`` it with the same session and inspect the
        ``Content-Type`` header — many exchanges return ``text/html``
        with a JS challenge instead of the actual PDF.
        """
        code = _strip_ts_suffix(ts_code)
        if not code:
            return None
        exchange = _exchange_for_code(code)
        if exchange is None:
            logger.info("ExchangeProvider: unknown exchange for %s", ts_code)
            return None

        earliest = target_date - timedelta(days=tolerance_days)
        latest = target_date + timedelta(days=tolerance_days)

        if exchange == "SSE":
            rows = self._fetch_sse(code, earliest, latest)
        elif exchange == "SZSE":
            rows = self._fetch_szse(code, earliest, latest)
        elif exchange == "BSE":
            rows = self._fetch_bse(code, earliest, latest)
        else:  # pragma: no cover - defensive
            return None

        if not rows:
            return None

        scored: list[tuple[tuple[int, int], str]] = []
        for row in rows:
            url = row.get("url") or ""
            if not url:
                continue
            t = row.get("date") or target_date
            if isinstance(t, datetime):
                t = t.date()
            if not isinstance(t, date):
                t = target_date
            date_penalty = abs((t - target_date).days)  # 0..tolerance
            ttl_score = _score(row.get("title", ""), title_hint)
            # Combined score: higher is better.  ``ttl_score`` dominates;
            # ``date_penalty`` is the tiebreaker.
            combined = (-ttl_score, date_penalty)
            scored.append((combined, url))

        if not scored:
            return None
        scored.sort(key=lambda x: x[0])
        return scored[0][1]

    def download_candidate(
        self,
        url: str,
        target: str,
        timeout: int = 60,
    ) -> tuple[bool, str | None, int | None]:
        """Best-effort download of ``url`` to ``target``.

        Returns ``(ok, error_message, content_length_bytes)``.  ``ok``
        is ``True`` only when the response is HTTP 200 AND the first
        5 bytes look like ``%PDF-`` (we don't trust Content-Type
        alone because some exchanges return text/html challenges).
        """
        try:
            with self.session.get(
                url, timeout=timeout, stream=True, allow_redirects=True
            ) as resp:
                if resp.status_code != 200:
                    return False, f"HTTP {resp.status_code}", None
                # Quick peek at the first chunk to detect the
                # ``acw_sc__v2`` JS challenge page that SSE returns
                # when anti-bot triggers fire.
                first = next(resp.iter_content(chunk_size=8), b"")
                if not first.lstrip().startswith(b"%PDF"):
                    msg = (
                        "non-PDF response (likely anti-bot challenge)"
                    )
                    logger.warning("ExchangeProvider: %s for %s", msg, url)
                    return False, msg, None
                with open(target, "wb") as fh:
                    fh.write(first)
                    for chunk in resp.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            fh.write(chunk)
        except requests.RequestException as exc:
            return False, f"network error: {exc}", None
        except OSError as exc:
            return False, f"io error: {exc}", None

        try:
            size = __import__("os").path.getsize(target)
        except OSError:  # pragma: no cover - defensive
            size = None
        return True, None, size

    # ----- exchange helpers ------------------------------------------

    def _fetch_sse(
        self,
        code: str,
        earliest: date,
        latest: date,
    ) -> list[dict[str, Any]]:
        """Query ``queryCompanyBulletinNew.do`` for one ``code``."""
        rows: list[dict[str, Any]] = []
        # We bind SECCode once.  pageHelp.pageSize caps each page
        # at 25; an A-share typically publishes a few periodic reports
        # per quarter so 5 pages = 125 records is plenty.
        params = {
            "isPagination": "true",
            "pageHelp.pageSize": "25",
            "pageHelp.beginPage": "1",
            "pageHelp.cacheSize": "1",
            "pageHelp.endPage": "5",
            "START_DATE": earliest.isoformat(),
            "END_DATE": latest.isoformat(),
            "SECURITY_CODE": code,
        }
        try:
            resp = self.session.get(
                _SSE_LIST_URL,
                params=params,
                headers={
                    **self.session.headers,
                    "Referer": "https://www.sse.com.cn/disclosure/listedinfo/announcement/",
                },
                timeout=_REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.warning("ExchangeProvider.SSE: request failed: %s", exc)
            return rows

        if resp.status_code != 200:
            logger.warning("ExchangeProvider.SSE: HTTP %s", resp.status_code)
            return rows

        try:
            data = resp.json()
        except ValueError:
            logger.warning("ExchangeProvider.SSE: bad JSON")
            return rows

        # The new endpoint nests rows under ``pageHelp.data`` and each
        # item is wrapped in an extra list (some SSE versions only).
        items = (
            (data.get("pageHelp") or {}).get("data")
            or data.get("data")
            or []
        )
        for item in items:
            # Unwrap single-element list.
            if isinstance(item, list) and item:
                item = item[0]
            if not isinstance(item, dict):
                continue
            url_path = item.get("URL") or item.get("url")
            if not url_path:
                continue
            rows.append(
                {
                    "title": item.get("TITLE") or item.get("title") or "",
                    "url": url_path if url_path.startswith("http")
                    else _SSE_STATIC_BASE + (url_path if url_path.startswith("/") else "/" + url_path),
                    "date": _parse_sse_date(item.get("SSEDATE")),
                }
            )
        return rows

    def _fetch_szse(
        self,
        code: str,
        earliest: date,
        latest: date,
    ) -> list[dict[str, Any]]:
        """POST to ``/api/disc/announcement/annList`` for one ``code``."""
        rows: list[dict[str, Any]] = []
        body = {
            "seDate": [earliest.isoformat(), latest.isoformat()],
            "stock": [code],
            "channelCode": ["listedNotice_disc"],
            "pageSize": 30,
            "pageNum": 1,
            "random": "0.5",
        }
        try:
            resp = self.session.post(
                _SZSE_LIST_URL,
                params={"random": "0.5"},
                headers={
                    **self.session.headers,
                    "Referer": "http://www.szse.cn/disclosure/listed/notice/index.html",
                    "Content-Type": "application/json",
                    "X-Request-Type": "ajax",
                },
                data=json.dumps(body),
                timeout=_REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.warning("ExchangeProvider.SZSE: request failed: %s", exc)
            return rows

        if resp.status_code != 200:
            logger.warning("ExchangeProvider.SZSE: HTTP %s", resp.status_code)
            return rows

        try:
            data = resp.json()
        except ValueError:
            logger.warning("ExchangeProvider.SZSE: bad JSON")
            return rows

        for item in data.get("data") or []:
            attach_path = item.get("attachPath") or ""
            if not attach_path:
                continue
            url = (
                attach_path
                if attach_path.startswith("http")
                else _SZSE_STATIC_BASE + attach_path
                if attach_path.startswith("/")
                else _SZSE_STATIC_BASE + "/" + attach_path
            )
            rows.append(
                {
                    "title": item.get("title") or "",
                    "url": url,
                    "date": _parse_szse_date(item.get("publishTime")),
                }
            )
        return rows

    def _fetch_bse(
        self,
        code: str,
        earliest: date,
        latest: date,
    ) -> list[dict[str, Any]]:
        """BSE listing endpoint.

        BSE's CDN appears to return a 302 challenge to unauthenticated
        clients, so we can't reliably parse anything.  Return ``[]``
        and let the operator plug in a browser-automation tool if
        they ever need BSE coverage.
        """
        logger.info(
            "ExchangeProvider.BSE: endpoint blocked (302 challenge) — "
            "no BSE coverage for %s",
            code,
        )
        return []


# ---------------------------------------------------------------------------
# date helpers
# ---------------------------------------------------------------------------


def _parse_sse_date(raw: Any) -> date | None:
    """``2026-06-22`` or ``2026-06-22 09:00:00`` → date."""
    if not raw:
        return None
    s = str(raw).strip().split(" ")[0]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_szse_date(raw: Any) -> date | None:
    """``2026-06-26 00:00:00`` → date."""
    if not raw:
        return None
    s = str(raw).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


__all__ = ["ExchangeProvider", "_exchange_for_code"]
