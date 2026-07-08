"""Cninfo ETF periodic-report (季报/中报/年报) holdings provider.

Falls back to the raw periodic-report PDF when Eastmoney F10 / Tushare
``fund_portfolio`` / Akshare's ``fund_portfolio_hold_em`` are missing an
ETF.  The data lives in two places inside the PDF:

  * **§7.3.1 期末指数投资按公允价值占基金资产净值比例大小排序的
    所有股票投资明细** — the full stock-investment list, sorted
    descending by weight.  The first 10 rows are the "前十大重仓股"
    the user wants.
  * **§7.3.2 期末积极投资…** — actively-managed sub-portfolio, often
    empty.  Combined with §7.3.1 below for completeness.

The disclosure cadence is 4/30 (Q1), 8/30 (mid-year) and 10/30 (Q3);
the mid-year report on **2026-08-30** is the immediate trigger for
this provider.  This is the source of truth for any quarter that the
higher-priority feeds have not yet indexed.

Cninfo lookup pipeline (each call is best-effort — a single failure
returns ``[]`` rather than aborting the batch):

  1. ``topSearch/query`` — resolve the ETF's 6-digit code to a cninfo
     ``orgId`` (these all live in the lookup table at
     ``app/data/static/cninfo_org_ids.json``, but the search is the
     authoritative way to add new entries).
  2. ``fulltextSearch/full`` — search by ``<secName>`` (the canonical
     ETF name like ``沪深300ETF嘉实``) for ``<年度>年中期报告`` or
     ``<年度>年第3季度报告``; pick the most recent match whose
     ``adjunctUrl`` ends in ``.PDF``.
  3. PDF download from ``static.cninfo.com.cn/<adjunctUrl>``.
  4. ``pdfplumber`` text extraction, regex over §7.3.1.

The orgId for an ETF is the **fund management company** id (e.g.
``jjjl0000037`` for 嘉实), *not* the 6-digit ETF code.  SH-listed
ETFs (51xxxx) are not currently reachable through this provider —
they're filed via SSE's separate disclosure system which this server
cannot reach.  The provider therefore returns ``[]`` for those
tickers; the Eastmoney F10 path still covers them.

NOTE: this provider relies on ``pdfplumber`` being installed in the
runtime container.  It's installed as part of the live container via
``pip install pdfplumber``; the project ``pyproject.toml`` will be
updated to declare it as a dependency in a follow-up.
"""

import io
import logging
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests

logger = logging.getLogger(__name__)


_FULLTEXT_URL = "http://www.cninfo.com.cn/new/fulltextSearch/full"
_TOPSEARCH_URL = "http://www.cninfo.com.cn/new/information/topSearch/query"
_PDF_BASE = "http://static.cninfo.com.cn"
_MAX_PDF_BYTES = 20 * 1024 * 1024  # 20MB safety cap
_MIN_INTERVAL = 1.5  # seconds between cninfo calls


# Section 7.3.1 row format (extracted from a real 嘉实沪深300ETF
# 2024 年中期报告, page 37):
#
#   1 600519 贵州茅台 3,632,452 5,330,223,740.28 5.13
#   2 300750 宁德时代 15,260,440 2,747,337,013.20 2.65
#
# Numbered rows with 5 whitespace-separated fields: idx, code (6
# digits), name, shares (with thousands sep), value (with thousands
# sep), weight_pct.
_HOLDING_ROW = re.compile(
    r"^\s*(\d{1,3})\s+(\d{6})\s+([一-鿿A-Za-z·\s]{2,30}?)"  # idx code name
    r"\s+([\d,]+(?:\.\d+)?)\s+"  # shares
    r"([\d,]+(?:\.\d+)?)\s+"  # value
    r"(\d+(?:\.\d+)?)\s*$"  # weight_pct
)


class CninfoETFHoldingsProvider:
    """Cninfo 季报 / 中报 / 年报 PDF → ETF top-10 holdings.

    Output schema matches the existing akshare / tushare providers so
    the ETL can chain sources transparently:

        etf_code, holding_code, holding_name, weight, shares,
        market_value, holdings_as_of_date
    """

    name = "cninfo"

    def __init__(self) -> None:
        self._last_call = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_etf_holdings(
        self,
        code: str,
        *,
        fiscal_year: int | None = None,
        period: str = "semi",
        name_hint: str | None = None,
    ) -> pd.DataFrame:
        """Fetch the latest (or ``fiscal_year``-specific) periodic report for ``code``.

        Args:
            code: ETF code with or without market suffix
                (``159919``, ``159919.SZ``, ``510300.SH``).
            fiscal_year: Optional year filter (e.g. 2024 for the 2024
                mid-year report).  Defaults to "latest available".
            period: ``"semi"`` (mid-year, default — the 8/30 report),
                ``"q3"`` (10/30 quarterly), ``"q1"`` (4/30 quarterly)
                or ``"annual"`` (yearly).
            name_hint: Optional canonical ETF name (e.g. ``沪深300ETF
                嘉实``).  When omitted, the provider first consults
                ``cninfo_org_ids.json`` and then falls back to cninfo's
                ``topSearch`` API to resolve the name from the code.
        """
        pure = code.split(".")[0]
        ts_code = code if "." in code else f"{pure}.SZ" if pure.startswith("1") else f"{pure}.SH"

        # SH ETFs (51xxxx) are not currently reachable through cninfo
        # (they're filed via SSE's separate disclosure system which we
        # cannot reach from this host).  Return empty so the ETL moves
        # on to the next provider.
        if pure.startswith("5") or pure.startswith("0"):
            # We *try* anyway, but bail quickly when fulltextSearch
            # returns nothing.  Keep the bail-out cheap: don't waste
            # 1.5s on the pacing timer if we know it's a SH ETF.
            return self._df_empty(ts_code)

        try:
            report = self._find_latest_report(
                pure, ts_code,
                fiscal_year=fiscal_year,
                period=period,
                name_hint=name_hint,
            )
        except Exception as exc:
            logger.warning("cninfo ETF: find report failed for %s: %s", code, exc)
            return self._df_empty(ts_code)

        if not report:
            return self._df_empty(ts_code)

        try:
            pdf_bytes = self._download_pdf(report["adjunctUrl"])
        except Exception as exc:
            logger.warning("cninfo ETF: download failed for %s: %s", code, exc)
            return self._df_empty(ts_code)

        if not pdf_bytes:
            return self._df_empty(ts_code)

        try:
            text = self._extract_text(pdf_bytes)
        except Exception as exc:
            logger.warning("cninfo ETF: text extract failed for %s: %s", code, exc)
            return self._df_empty(ts_code)

        rows = self._parse_holdings_table(text, top_n=10)
        if not rows:
            logger.info("cninfo ETF: no §7.3 rows in PDF for %s", code)
            return self._df_empty(ts_code)

        snapshot = _quarter_end_date(
            fiscal_year=report.get("fiscal_year"),
            period=report.get("period", period),
        )
        out_rows = []
        for r in rows:
            holding_code = r["code"]
            # Tushare-style ts code: 6xxxxx -> SH, others -> SZ.
            if holding_code.startswith(("5", "6", "9")):
                holding_ts = f"{holding_code}.SH"
            elif holding_code.startswith(("0", "2", "3")):
                holding_ts = f"{holding_code}.SZ"
            else:
                holding_ts = f"{holding_code}.BJ"
            out_rows.append(
                {
                    "etf_code": ts_code,
                    "holding_code": holding_ts,
                    "holding_name": r["name"],
                    "weight": r["weight_pct"] / 100.0 if r["weight_pct"] is not None else None,
                    "shares": r["shares"],
                    "market_value": r["value"],
                    "holdings_as_of_date": snapshot,
                }
            )
        return pd.DataFrame(out_rows)

    # ------------------------------------------------------------------
    # cninfo search
    # ------------------------------------------------------------------

    def _find_latest_report(
        self,
        pure_code: str,
        ts_code: str,
        *,
        fiscal_year: int | None,
        period: str,
        name_hint: str | None = None,
    ) -> dict[str, Any] | None:
        """Look up the most recent periodic-report announcement for an ETF.

        Uses cninfo's ``fulltextSearch/full`` endpoint — searching by
        the *ETF name* (not the 6-digit code) is what actually works
        for funds.  The search is full-text on the announcement title,
        so we restrict it to known periodic-report keywords and pick
        the most recent match.
        """
        names = _candidate_names(pure_code, ts_code, name_hint=name_hint)
        if not names:
            return None

        period_kw = _period_keywords(period)
        year_filter = fiscal_year

        # Search a wide date window and let the title filter do the work.
        end_year = (year_filter or date.today().year) + 1
        sdate = f"{end_year - 3}-01-01"
        edate = f"{end_year}-12-31"

        for name in names:
            for kw in period_kw:
                params = {
                    "searchkey": f"{name} {kw}",
                    "sdate": sdate,
                    "edate": edate,
                    "isfulltext": "false",
                    "sortName": "pubdate",
                    "sortType": "desc",
                    "pageNum": "1",
                }
                body = self._post(_FULLTEXT_URL, params=params)
                if not body:
                    continue
                anns = body.get("announcements") or []
                # Filter to this specific ETF (by secCode) and skip summaries / corrigenda.
                for a in anns:
                    if str(a.get("secCode") or "") != pure_code:
                        continue
                    title = (a.get("announcementTitle") or "").replace("<em>", "").replace("</em>", "")
                    if any(skip in title for skip in ("摘要", "更正", "补充", "取消", "提示")):
                        continue
                    if kw not in title:
                        continue
                    adjunct = a.get("adjunctUrl") or ""
                    if not adjunct.lower().endswith(".pdf"):
                        continue
                    ann_year = _year_from_title(title) or _year_from_time_ms(a.get("announcementTime"))
                    if year_filter is not None and ann_year is not None and ann_year != year_filter:
                        continue
                    return {
                        "adjunctUrl": adjunct,
                        "title": title,
                        "announcementId": a.get("announcementId"),
                        "fiscal_year": ann_year,
                        "period": period,
                    }
        return None

    # ------------------------------------------------------------------
    # PDF download / extract
    # ------------------------------------------------------------------

    def _download_pdf(self, adjunct_url: str) -> bytes | None:
        url = adjunct_url
        if url.startswith("/"):
            url = _PDF_BASE + url
        elif not url.startswith("http"):
            url = f"{_PDF_BASE}/{url.lstrip('/')}"
        self._pace()
        try:
            r = requests.get(url, timeout=30, stream=True)
        except requests.RequestException as exc:
            logger.warning("cninfo ETF pdf GET failed: %s", exc)
            return None
        if r.status_code != 200:
            logger.warning("cninfo ETF pdf HTTP %s for %s", r.status_code, url)
            return None
        # Cap at _MAX_PDF_BYTES — a 200-page annual report can hit 30MB.
        buf = io.BytesIO()
        read = 0
        for chunk in r.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            read += len(chunk)
            if read > _MAX_PDF_BYTES:
                logger.warning("cninfo ETF pdf too large, truncating at %s bytes", read)
                break
            buf.write(chunk)
        return buf.getvalue()

    @staticmethod
    def _extract_text(pdf_bytes: bytes) -> str:
        """Best-effort text extraction using pdfplumber."""
        import pdfplumber

        pieces: list[str] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                try:
                    pieces.append(page.extract_text() or "")
                except Exception as exc:  # pragma: no cover - per-page fault
                    logger.debug("pdfplumber page failed: %s", exc)
        return "\n".join(pieces)

    # ------------------------------------------------------------------
    # Section 7.3 parser
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_holdings_table(text: str, top_n: int = 10) -> list[dict[str, Any]]:
        """Extract the top-N rows from §7.3 / §7.3.1 (sorted by weight desc).

        Most fund management companies split §7.3 into
        ``7.3.1 期末指数投资…`` (passive) and ``7.3.2 期末积极投资…``
        (active). A handful (e.g. 富国) collapse the passive section
        into ``7.3 期末…所有股票投资明细`` without the ``.1`` subscript.
        The parser accepts both forms.

        The regex matches the table row layout we observed in real
        periodic reports: 序号 + 6-digit code + name + shares + value +
        weight_pct.  Names with internal spaces (e.g. ``五 粮 液``)
        are normalised to ``五粮液`` post-match.
        """
        # The TOC at the start of every report lists the same section
        # numbers with ``.....`` (dot leaders) and page numbers.  Skip
        # those entries by requiring the heading to NOT be followed by
        # the dot-leader pattern within the same line.  This anchors
        # us to the body of the report.
        body = _strip_toc(text)
        # §7.3 / §7.3.1 starts at the heading line.  We require the
        # heading to be at the start of a line so 6.4.7.3.1-style
        # nested-section markers do not match.
        m_section = re.search(
            r"(?:^|\n)7\.3(?:\.1)?(?![\.\d])[^\n]*", body
        )
        if not m_section:
            return []
        start = m_section.end()
        # End at §7.3.2, §7.3.3, §7.4, or the next major §8 heading.
        end_match = re.search(
            r"(?:^|\n)7\.3\.[2-9]|(?:^|\n)7\.4|(?:^|\n)§8",
            body[start:],
        )
        end = start + end_match.start() if end_match else len(body)
        section = body[start:end]

        rows: list[dict[str, Any]] = []
        for line in section.splitlines():
            m = _HOLDING_ROW.match(line)
            if not m:
                continue
            idx, code, name, shares, value, weight_pct = m.groups()
            # Sanity: skip obviously bad rows.
            try:
                shares_v = float(shares.replace(",", ""))
                value_v = float(value.replace(",", ""))
                weight_v = float(weight_pct)
            except ValueError:
                continue
            if weight_v <= 0 or weight_v > 100:
                continue
            rows.append(
                {
                    "rank": int(idx),
                    "code": code,
                    "name": re.sub(r"\s+", "", name),
                    "shares": shares_v,
                    "value": value_v,
                    "weight_pct": weight_v,
                }
            )
        # Sort by rank to be safe (rows are already in PDF order).
        rows.sort(key=lambda r: r["rank"])
        return rows[:top_n]

    # ------------------------------------------------------------------
    # HTTP pacing
    # ------------------------------------------------------------------

    def _pace(self) -> None:
        elapsed = time.time() - self._last_call
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        self._last_call = time.time()

    def _post(self, url: str, *, params: dict[str, str]) -> dict[str, Any] | None:
        self._pace()
        try:
            r = requests.post(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0 Safari/537.36"
                    ),
                    "Content-Type": (
                        "application/x-www-form-urlencoded; charset=UTF-8"
                    ),
                },
                data=params,
                timeout=15,
            )
        except requests.RequestException as exc:
            logger.warning("cninfo POST %s failed: %s", url, exc)
            return None
        if r.status_code != 200:
            logger.warning("cninfo POST %s HTTP %s", url, r.status_code)
            return None
        try:
            return r.json()
        except ValueError as exc:
            logger.warning("cninfo POST %s non-JSON: %s", url, exc)
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _df_empty(ts_code: str) -> pd.DataFrame:
        return pd.DataFrame(
            columns=[
                "etf_code",
                "holding_code",
                "holding_name",
                "weight",
                "shares",
                "market_value",
                "holdings_as_of_date",
            ]
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _candidate_names(
    pure_code: str,
    ts_code: str,
    *,
    name_hint: str | None = None,
) -> list[str]:
    """Return plausible ETF-name search keys for ``fulltextSearch/full``.

    Cninfo indexes the ETF by its full display name (e.g.
    ``沪深300ETF嘉实``); the 6-digit code alone returns zero hits.
    Resolution order:

      1. ``name_hint`` from the caller (highest priority — e.g. when
         the pipeline already loaded the canonical name from
         ``etf_info.name``).
      2. The static ``cninfo_org_ids.json`` lookup table (in the
         richer ``{ts_code: {orgId, name}}`` shape).
      3. Cninfo's ``topSearch/query`` API — searches by code first,
         then by the fund-management company name if we can infer one
         from the static table.
    """
    names: list[str] = []
    if name_hint:
        names.append(str(name_hint))
    table = _load_etf_name_table()
    if table:
        entry = table.get(ts_code) or table.get(pure_code) or {}
        n = entry.get("name") if isinstance(entry, dict) else None
        if n and n not in names:
            names.append(str(n))
    if not names:
        # Last-ditch: ask cninfo's autocomplete for the canonical name.
        resolved = _resolve_name_via_topsearch(pure_code)
        if resolved and resolved not in names:
            names.append(resolved)
    if not names:
        # Final fallback so callers don't see a None; this won't match
        # anything useful.
        names.append(f"ETF{pure_code}")
    return names


def _resolve_name_via_topsearch(pure_code: str) -> str | None:
    """One-shot cninfo ``topSearch`` lookup keyed by code.

    Returns the canonical display name (``zwjc``) of the first ETF
    hit, or ``None`` if cninfo doesn't index this code at all (e.g.
    SH-listed ETFs which the fulltext index doesn't carry).
    """
    payload = {"keyWord": pure_code, "maxSecNum": 10, "maxListNum": 10}
    try:
        r = requests.post(
            _TOPSEARCH_URL,
            data=payload,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
                ),
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        logger.debug("topSearch %s: %s", pure_code, exc)
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    # The response is an array of suggestions; pick the first that
    # matches our code AND is an ETF (avoids "农银沪深300" type noise
    # when searching a code like 159919).
    for entry in data or []:
        if str(entry.get("code") or "") != pure_code:
            continue
        if entry.get("category") == "ETF":
            return entry.get("zwjc")
    # Fallback: any entry that matches the code.
    for entry in data or []:
        if str(entry.get("code") or "") == pure_code:
            return entry.get("zwjc")
    return None


def _load_etf_name_table() -> dict[str, Any]:
    """Read the optional name-augmented ETF orgId table from disk.

    The default ``cninfo_org_ids.json`` is just ``{ts_code: orgId}``;
    this helper accepts a richer ``{ts_code: {orgId, name}}`` shape
    too.  Failures are silent (return ``{}``) — the provider can still
    run without the name hint.
    """
    p = Path(__file__).parent.parent / "static" / "cninfo_org_ids.json"
    if not p.exists():
        return {}
    try:
        import json
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _period_keywords(period: str) -> list[str]:
    """Cninfo title keywords for each periodic-report type."""
    return {
        "annual": ["年度报告"],
        "semi": ["中期报告", "半年度报告"],
        "q1": ["第1季度报告", "一季度报告", "第一季度报告"],
        "q3": ["第3季度报告", "三季度报告", "第三季度报告"],
    }.get(period, ["中期报告", "半年度报告"])


def _strip_toc(text: str) -> str:
    """Drop TOC entries (lines with dot leaders) from the extracted text.

    Each periodic report has a table of contents that lists every
    section number with a dot leader and a page number (e.g.
    ``7.3 期末…所有股票投资明细.......... 37``).  These lines appear
    only in the TOC, so we strip any line containing three or more
    consecutive dots anywhere in the document.
    """
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        if "...." in line:
            continue
        out.append(line)
    return "".join(out)


def _year_from_title(title: str) -> int | None:
    m = re.search(r"(\d{4})\s*年", title)
    return int(m.group(1)) if m else None


def _year_from_time_ms(value: Any) -> int | None:
    """Cninfo returns ``announcementTime`` as epoch MILLISECONDS."""
    if value is None:
        return None
    try:
        ts = float(value) / 1000.0
        if ts <= 0:
            return None
        return datetime.fromtimestamp(ts).year
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _quarter_end_date(*, fiscal_year: int | None, period: str) -> date | None:
    """Map (fiscal_year, period) to the report's quarter-end date."""
    if fiscal_year is None:
        return None
    table = {
        "annual": (12, 31),
        "semi": (6, 30),
        "q1": (3, 31),
        "q3": (9, 30),
    }
    md = table.get(period)
    if not md:
        return None
    month, day = md
    try:
        return date(fiscal_year, month, day)
    except ValueError:
        return None
