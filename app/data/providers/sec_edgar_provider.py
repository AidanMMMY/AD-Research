"""SEC EDGAR public-data provider.

Free public API at https://data.sec.gov/ — no API key required, but the
SEC enforces two hard rules:

  1. Every request MUST include a descriptive User-Agent that points
     to a real person / contact (the SEC blocks anonymous UAs with 403).
  2. Aggregate request rate MUST stay under 10 req/sec across the
     full data.sec.gov origin.  We pace ourselves at ~9 req/sec
     (``_MIN_INTERVAL_SECONDS = 0.11``) to leave headroom for other
     in-house workers hitting the same origin.

Endpoints used:

  - ``https://www.sec.gov/files/company_tickers.json``
        Full directory of all SEC-registered tickers → CIK.  Cached
        on disk to ``app/data/static/sec_tickers.json`` so the cold-start
        path doesn't re-hit SEC on every restart.
  - ``https://data.sec.gov/submissions/CIK{cik_padded10}.json``
        Per-company metadata + the full filing history
        (form type, filing date, accession number, primary document).
  - ``https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded10}.json``
        Per-company GAAP / IFRS XBRL facts.  ``extract_metrics`` reads
        the 4-6 most-asked concepts (Revenue, Net Income, Assets,
        Stockholders' Equity) for the requested ticker.

Why no 8-K: 8-Ks are dense event filings (5-10/day per large issuer);
the value density is much lower than for 10-K/10-Q/20-F and the
filing volume would blow the rate limit.  Callers that need 8-K data
should hit the raw ``fetch_submissions`` payload.
"""

import json
import logging
import os
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)


# ─── SEC policy constants ──────────────────────────────────────────────
# SEC requires every request to carry a UA that identifies the requester.
# Override via SEC_USER_AGENT in the environment when you have a real
# production contact (e.g. "AlloyResearch ops@alloy-research.example.com").
DEFAULT_USER_AGENT = "AlloyResearch research@example.com"

# Submissions / facts endpoints live under data.sec.gov which has a
# documented 10 req/sec limit.  0.11s pacing keeps us safely below that.
_MIN_INTERVAL_SECONDS = 0.11

# company_tickers.json is served from www.sec.gov with a more lenient
# policy but we still pace ourselves to be polite.
_INDEX_MIN_INTERVAL_SECONDS = 0.5

_REQUEST_TIMEOUT_SECONDS = 20
_MAX_RETRIES = 3

# GAAP / IFRS concept tags we attempt to extract.  Different companies
# report under US-GAAP or IFRS (for foreign private issuers), so we
# check both namespaces.  Order matters: the first match wins.
_TARGET_CONCEPTS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "NetIncomeLoss",
    "Assets",
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
]

# Form types worth ingesting.  8-K is excluded intentionally — see
# module docstring.
_TARGET_FORM_TYPES = {"10-K", "10-Q", "20-F", "20-F/A", "10-K/A", "10-Q/A"}


# ─── Disk-cached ticker directory ──────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_STATIC_DIR = _HERE.parent / "static"
_TICKER_CACHE_PATH = _STATIC_DIR / "sec_tickers.json"


# ─── HTTP helpers ──────────────────────────────────────────────────────
def _resolve_user_agent() -> str:
    """Return the SEC User-Agent, preferring env var override.

    The SEC's enforcement team will block requests that lack a UA with
    a real email address.  We bake in a sensible default and let ops
    override at deploy time without touching code.
    """
    return (
        os.environ.get("SEC_USER_AGENT", "").strip()
        or DEFAULT_USER_AGENT
    )


class SecEdgarProvider:
    """HTTP client for the public SEC EDGAR data API."""

    DATA_BASE = "https://data.sec.gov"
    WWW_BASE = "https://www.sec.gov"

    @property
    def name(self) -> str:
        return "sec_edgar"

    def __init__(self, user_agent: str | None = None) -> None:
        self.user_agent = (user_agent or _resolve_user_agent()).strip() or DEFAULT_USER_AGENT
        # Use a single ``requests.Session`` so the underlying connection
        # pool reuses TLS handshakes across the full crawl.
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Host": "data.sec.gov",
        })
        self._last_request_ts: float = 0.0
        self._last_index_ts: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_ticker_to_cik_map(
        self,
        force_refresh: bool = False,
        cache_path: Path | None = None,
    ) -> dict[str, str]:
        """Return ``{ticker: 10-digit CIK}`` for the full SEC universe.

        Result is cached on disk in ``app/data/static/sec_tickers.json``
        so the cold start is fast.  Pass ``force_refresh=True`` to
        bypass the cache (e.g. after a regulator CIK renumbering).

        The remote payload is structured as a list of records::

            [{"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...]

        We normalise it into a flat dict keyed by uppercase ticker.
        """
        path = Path(cache_path) if cache_path else _TICKER_CACHE_PATH
        if not force_refresh and path.exists():
            try:
                with path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                tickers = data.get("tickers") or data
                if isinstance(tickers, dict) and tickers:
                    return {
                        str(t).upper(): str(v.get("cik") if isinstance(v, dict) else v)
                        for t, v in tickers.items()
                    }
                if isinstance(tickers, list) and tickers:
                    return self._tickers_list_to_map(tickers)
            except Exception as exc:  # noqa: BLE001 - fallback to network
                logger.warning("SEC ticker cache read failed (%s); refetching", exc)

        # Cache miss — hit the network.
        url = f"{self.WWW_BASE}/files/company_tickers.json"
        self._throttle_index()
        try:
            resp = self._session.get(url, timeout=_REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("SEC ticker index fetch failed: %s", exc)
            return {}

        try:
            payload = resp.json()
        except ValueError as exc:
            logger.warning("SEC ticker index returned non-JSON payload: %s", exc)
            return {}

        tickers = self._tickers_list_to_map(payload)
        # Persist to disk so subsequent cold starts skip the network.
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "tickers": {t: {"cik": c} for t, c in tickers.items()},
                        "source": "https://www.sec.gov/files/company_tickers.json",
                        "generated_at": date.today().isoformat(),
                    },
                    fh,
                    ensure_ascii=False,
                    indent=2,
                )
        except OSError as exc:  # noqa: BLE001 - cache write is best-effort
            logger.warning("SEC ticker cache write failed: %s", exc)

        return tickers

    def fetch_submissions(self, cik: str) -> dict[str, Any]:
        """Return the raw ``submissions/CIK*.json`` payload for a CIK.

        The payload includes ``filings.recent`` (a list of dicts with
        ``form``, ``filingDate``, ``reportDate``, ``accessionNumber``,
        ``primaryDocument``) plus a ``filings.files`` list for older
        archives.  Callers should treat this as opaque — schema drifts
        over time and we isolate the parsing to
        ``_parse_recent_filings``.
        """
        cik_padded = self._pad_cik(cik)
        url = f"{self.DATA_BASE}/submissions/CIK{cik_padded}.json"
        return self._get_json(url, namespace="data")

    def fetch_company_facts(self, cik: str) -> dict[str, Any]:
        """Return the full ``companyfacts`` payload for a CIK.

        This is the raw XBRL fact dump.  ``extract_metrics`` reads a
        narrow subset of it (Revenue, Net Income, Assets, Equity).
        """
        cik_padded = self._pad_cik(cik)
        url = f"{self.DATA_BASE}/api/xbrl/companyfacts/CIK{cik_padded}.json"
        return self._get_json(url, namespace="data")

    def extract_metrics(
        self, facts: dict[str, Any], tickers: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Pull a handful of core GAAP concepts from a facts payload.

        Returns a list of ``{ticker, concept, value, period_end,
        fy, fp, fp, form, filed}`` dicts — one per (concept, period).
        Tickers is a hint used to label the rows; when ``None`` the
        row's ticker is left empty (callers usually have it).
        """
        if not isinstance(facts, dict):
            return []

        entity = facts.get("entityName") or ""
        facts_root = facts.get("facts") or {}
        us_gaap = facts_root.get("us-gaap") or {}
        ifrs = facts_root.get("ifrs-full") or {}

        ticker_label = (tickers or [None])[0] if tickers else None

        out: list[dict[str, Any]] = []
        for concept in _TARGET_CONCEPTS:
            units = us_gaap.get(concept) or ifrs.get(concept)
            if not units:
                continue
            usd = units.get("USD") or units.get("USD/shares")
            if not usd:
                continue
            # Each entry in USD is a single (period, value) datapoint
            # — we want only the most recent FY and the most recent
            # quarterly for the headline number.
            for entry in usd:
                val = entry.get("val")
                if val is None:
                    continue
                out.append(
                    {
                        "ticker": ticker_label or "",
                        "entity_name": entity,
                        "concept": concept,
                        "value": val,
                        "period_end": entry.get("end"),
                        "period_start": entry.get("start"),
                        "form": entry.get("form"),
                        "filed": entry.get("filed"),
                        "fy": entry.get("fy"),
                        "fp": entry.get("fp"),
                        "frame": entry.get("frame"),
                    }
                )
        return out

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _get_json(self, url: str, namespace: str = "data") -> dict[str, Any]:
        """GET ``url`` and return parsed JSON, honouring rate limits.

        ``namespace`` is either ``"data"`` (data.sec.gov, 0.11s
        throttle) or ``"www"`` (www.sec.gov, 0.5s throttle).  We
        rewrite the ``Host`` header to match the origin we're hitting
        so the SEC's load balancer doesn't think we're being sneaky.
        """
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                if namespace == "www":
                    self._session.headers["Host"] = "www.sec.gov"
                    self._throttle_index()
                else:
                    self._session.headers["Host"] = "data.sec.gov"
                    self._throttle_data()
                resp = self._session.get(url, timeout=_REQUEST_TIMEOUT_SECONDS)
            except requests.RequestException as exc:
                last_error = exc
                logger.warning(
                    "SEC request %s failed (attempt %d/%d): %s",
                    url, attempt + 1, _MAX_RETRIES, exc,
                )
                time.sleep(2 * (attempt + 1))
                continue

            if resp.status_code == 429:
                # Be a good citizen — sleep generously and retry once.
                retry_after = float(resp.headers.get("Retry-After", 10))
                logger.warning(
                    "SEC 429 rate-limited; sleeping %.1fs (attempt %d/%d)",
                    retry_after, attempt + 1, _MAX_RETRIES,
                )
                time.sleep(max(retry_after, 10))
                continue

            if 500 <= resp.status_code < 600:
                last_error = RuntimeError(f"SEC HTTP {resp.status_code}")
                time.sleep(2 * (attempt + 1))
                continue

            try:
                resp.raise_for_status()
            except requests.HTTPError as exc:
                # Most often: 403 because the User-Agent is wrong.  We
                # log the URL + UA so ops can debug.
                logger.error(
                    "SEC HTTP %s for %s (User-Agent=%r)",
                    resp.status_code, url, self.user_agent,
                )
                raise RuntimeError(
                    f"SEC HTTP {resp.status_code}: {resp.text[:200]}"
                ) from exc

            try:
                return resp.json()
            except ValueError as exc:
                raise RuntimeError(
                    f"SEC response was not valid JSON: {exc}"
                ) from exc

        raise RuntimeError(
            f"SEC request failed after {_MAX_RETRIES} attempts: {last_error}"
        )

    def _throttle_data(self) -> None:
        """Enforce ≥0.11s between calls to data.sec.gov."""
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < _MIN_INTERVAL_SECONDS:
            time.sleep(_MIN_INTERVAL_SECONDS - elapsed)
        self._last_request_ts = time.monotonic()

    def _throttle_index(self) -> None:
        """Enforce ≥0.5s between calls to www.sec.gov (index endpoints)."""
        elapsed = time.monotonic() - self._last_index_ts
        if elapsed < _INDEX_MIN_INTERVAL_SECONDS:
            time.sleep(_INDEX_MIN_INTERVAL_SECONDS - elapsed)
        self._last_index_ts = time.monotonic()

    @staticmethod
    def _pad_cik(cik: str) -> str:
        """Return ``cik`` zero-padded to SEC's 10-digit width.

        SEC's URL convention is ``CIK0000320193`` — 10 digits.  We
        accept either int or str input and never raise on bad input
        (the subsequent HTTP call will surface the problem with a
        clean 4xx).
        """
        digits = "".join(ch for ch in str(cik) if ch.isdigit())
        if not digits:
            return str(cik)
        return digits.zfill(10)

    @staticmethod
    def _tickers_list_to_map(payload: Any) -> dict[str, str]:
        """Normalise ``company_tickers.json`` into ``{ticker: cik}``."""
        if not isinstance(payload, list):
            return {}
        out: dict[str, str] = {}
        for row in payload:
            if not isinstance(row, dict):
                continue
            ticker = row.get("ticker")
            cik_raw = row.get("cik_str") or row.get("cik")
            if not ticker or cik_raw is None:
                continue
            out[str(ticker).upper()] = str(cik_raw).zfill(10)
        return out
