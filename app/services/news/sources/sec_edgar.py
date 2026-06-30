"""SEC EDGAR filings crawler.

Pulls recent corporate filings (8-K, 10-Q, 10-K, S-1) for a universe
of US-listed tickers. Uses the public EDGAR JSON API which is
rate-limited to **10 requests per second per IP**. We self-impose
10 req/min to be safe and SEC-friendly.

Endpoints
---------
* Company submissions JSON:
  ``https://data.sec.gov/submissions/CIK{CIK10}.json``
  CIK must be 10 digits (zero-padded).

We do NOT depend on any external CIK lookup; the caller supplies a
``ticker -> cik`` mapping (e.g. built from a static table or a prior
discovery job).

User-Agent
----------
SEC requires a descriptive User-Agent with contact information.
We default to ``"AD-Research admin@example.com"`` but allow override
via the ``SEC_USER_AGENT`` env var.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Iterable

import httpx

from app.services.news.crawler.rate_limiter import AsyncTokenBucket
from app.services.news.crawler.symbol_extractor import extract_symbols
from app.services.news.crawler.types import RawArticle

logger = logging.getLogger(__name__)

SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data"

# Only these filing types are kept. Everything else is filtered out
# to keep the news stream relevant for sentiment / catalyst tracking.
SUPPORTED_FORMS: frozenset[str] = frozenset({"8-K", "10-Q", "10-K", "S-1"})


def _to_internal(ticker: str) -> str:
    return f"{ticker.upper().strip()}.US"


def _pad_cik(cik: str | int) -> str:
    """Return a 10-digit zero-padded CIK, as required by data.sec.gov."""
    s = str(int(cik))
    return s.zfill(10)


class SecEdgarCrawler:
    """Crawl SEC EDGAR for recent filings of a US instrument universe."""

    source_name = "sec_edgar"
    rate_limit_per_min = 10
    timeout_seconds = 20.0

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        rate_limiter: AsyncTokenBucket | None = None,
        user_agent: str | None = None,
    ) -> None:
        self._client = client
        self._owns_client = client is None
        self._limiter = rate_limiter or AsyncTokenBucket(self.rate_limit_per_min)
        self._user_agent = user_agent or os.getenv(
            "SEC_USER_AGENT",
            "AD-Research admin@example.com",
        )

    async def __aenter__(self) -> "SecEdgarCrawler":
        if self._client is None:
            self._client = await self._build_client()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _build_client(self) -> httpx.AsyncClient:
        user_agent = self._user_agent

        async def _set_ua(request: httpx.Request) -> None:
            # SEC requires a real UA — httpx's default is rejected.
            request.headers["User-Agent"] = user_agent

        return httpx.AsyncClient(
            headers={
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=self.timeout_seconds,
            follow_redirects=True,
            event_hooks={"request": [_set_ua]},
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch(
        self,
        ticker_to_cik: dict[str, str | int],
        *,
        forms: Iterable[str] | None = None,
        since: datetime | None = None,
    ) -> list[RawArticle]:
        """Fetch recent filings for the supplied ``ticker -> CIK`` map.

        Args:
            ticker_to_cik: e.g. ``{"AAPL": "320193", "MSFT": "789019"}``.
            forms: Which filing forms to keep. Defaults to the
                module-level ``SUPPORTED_FORMS`` (8-K, 10-Q, 10-K, S-1).
            since: Optional cutoff. Filings with ``filingDate`` older
                than this are filtered out (UTC). When ``None`` we
                return whatever SEC has on the first page (typically
                ~40 most-recent filings per company).
        """
        forms_keep = {f.upper() for f in (forms or SUPPORTED_FORMS)}
        articles: list[RawArticle] = []
        async with self:
            for ticker, cik in ticker_to_cik.items():
                if not ticker or not cik:
                    continue
                try:
                    arts = await self._fetch_one(ticker, cik, forms_keep, since)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("SEC EDGAR failed for %s: %s", ticker, exc)
                    continue
                articles.extend(arts)
        return articles

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _fetch_one(
        self,
        ticker: str,
        cik: str | int,
        forms_keep: set[str],
        since: datetime | None,
    ) -> list[RawArticle]:
        await self._limiter.acquire()
        assert self._client is not None
        url = SEC_SUBMISSIONS_URL.format(cik=_pad_cik(cik))
        # SEC requires a descriptive User-Agent; inject it per-request so
        # callers passing in their own client still send a valid UA.
        resp = await self._client.get(
            url,
            headers={"User-Agent": self._user_agent},
        )
        resp.raise_for_status()
        data = resp.json()
        return _parse_submissions(data, ticker, cik, forms_keep, since)


# ---------------------------------------------------------------------------
# Pure parsing helpers (testable without HTTP)
# ---------------------------------------------------------------------------


def _parse_submissions(
    data: dict,
    ticker: str,
    cik: str | int,
    forms_keep: set[str],
    since: datetime | None,
) -> list[RawArticle]:
    """Convert a SEC submissions JSON payload into ``RawArticle``s."""
    recent = (data or {}).get("filings", {}).get("recent")
    if not recent:
        return []

    forms = recent.get("form") or []
    accession = recent.get("accessionNumber") or []
    primary = recent.get("primaryDocument") or []
    filed = recent.get("filingDate") or []
    report = recent.get("reportDate") or []
    primary_desc = recent.get("primaryDocDescription") or []
    items_field = recent.get("items") or []

    cik_padded = _pad_cik(cik)
    out: list[RawArticle] = []
    for i, form in enumerate(forms):
        if form not in forms_keep:
            continue
        acc = accession[i] if i < len(accession) else None
        doc = primary[i] if i < len(primary) else None
        filed_raw = filed[i] if i < len(filed) else None
        report_raw = report[i] if i < len(report) else None
        desc = primary_desc[i] if len(primary_desc) > i else ""
        items = items_field[i] if len(items_field) > i else ""

        if not acc or not doc or not filed_raw:
            continue

        published_at = _parse_iso_date(filed_raw)
        if published_at is None:
            continue
        if since is not None and published_at < since:
            continue

        acc_nodash = acc.replace("-", "")
        url = f"{SEC_ARCHIVE_BASE}/{int(cik)}/{acc_nodash}/{doc}"

        title = f"{form} — {ticker.upper()}" + (f" ({desc})" if desc else "")
        body = " | ".join(
            x for x in (desc, items, f"Filed: {filed_raw}", f"Period: {report_raw}") if x
        )

        art = RawArticle(
            source="sec_edgar",
            source_id=acc,
            url=url,
            title=title,
            published_at=published_at,
            body=body or None,
            author=ticker.upper(),
            language="en",
            market="us",
            extra={
                "ticker": ticker.upper(),
                "cik": cik_padded,
                "form": form,
                "items": items,
                "primary_doc": doc,
                "report_date": report_raw,
                "category": form,
            },
        )
        symbols = extract_symbols(f"{title}\n{body}", url=url)
        symbols.add(_to_internal(ticker))
        art.engagement = {"symbols_extracted": sorted(symbols)}
        out.append(art)
    return out


def _parse_iso_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
