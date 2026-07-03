"""Chinese-name lookup provider with a four-source fallback chain.

Primary source is East Money's ``push2.eastmoney.com`` API.  When the
upstream rate-limits us (502/RemoteDisconnected is common from server
IPs) or simply lacks the symbol, we step through three backup sources
in order:

    1. East Money (existing)
    2. Sina Finance   — ``https://hq.sinajs.cn/list=gb_{SYMBOL}``
                        CSV-ish payload, 2nd field is the Chinese name;
                        requires ``Referer: https://finance.sina.com.cn/``.
    3. Tencent Finance — ``https://qt.gtimg.cn/q=us{SYMBOL}``
                        ``~``-delimited payload, 2nd field is the
                        Chinese name; response is GBK-encoded.
    4. Yahoo Finance   — ``https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}``
                        Last-resort English name from ``meta.shortName``.
                        We accept English here rather than returning
                        ``None`` so the backfilled row is at least
                        not blank.

All four sources share the same ``requests.Session`` so the connection
pool (and any per-session rate-limiting headers) are reused.

Caching: in-process dict keyed by ``(source, market_id, symbol)``.
Positive hits cached for 24h; negative (no-data / exception) hits
cached for 5 minutes.  Cache keys include the source name so that
East Money's failure for a symbol does not poison Sina/Tencent/Yahoo
with a 5-minute blank.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Callable

import requests

logger = logging.getLogger(__name__)


_BASE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_TIMEOUT = 8.0
_CACHE_TTL_SECONDS = 24 * 3600
_NEGATIVE_CACHE_TTL = 300  # cache "not found" for 5 min to avoid retry storms

# Sentinel market_id used for sources that don't iterate secid prefixes.
_NO_MARKET_ID = 0

# Source identifiers used in cache keys and logging.
_SOURCE_EASTMONEY = "eastmoney"
_SOURCE_SINA = "sina"
_SOURCE_TENCENT = "tencent"
_SOURCE_YAHOO = "yahoo"

_FALLBACK_ORDER: tuple[str, ...] = (_SOURCE_SINA, _SOURCE_TENCENT, _SOURCE_YAHOO)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_us_market_id(symbol: str, exchange: str | None) -> list[int]:
    """Return the ordered list of East Money secid prefixes to try for a US symbol.

    Order is heuristic:
      * NASDAQ symbols are typically 4-5 letters (e.g. AAPL, MSFT, NVDA,
        but also PEP/IBM which are NYSE).  We rely on the explicit
        ``exchange`` first when present.
      * Symbols with 5 letters are usually NASDAQ; symbols with 1-4
        characters are usually NYSE/AMEX.
      * We always try both prefixes if the explicit guess misses.
    """
    sym = (symbol or "").strip().upper()
    exch = (exchange or "").strip().upper()

    if exch in {"NASDAQ", "NASDAQGS", "NASDAQGM", "NSDQ"}:
        return [106, 105]
    if exch in {"NYSE", "AMEX", "NYE", "ASE", "ARCX", "BATS"}:
        return [105, 106]
    # No exchange hint — heuristic on length and alpha content.
    if sym.isalpha() and len(sym) >= 5:
        return [106, 105]
    return [105, 106]


def _clean(value: Any) -> str | None:
    """Strip whitespace and return None when empty / non-string."""
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    return value or None


_CJK_PATTERN = re.compile(r"[㐀-䶿一-鿿豈-﫿]")


def _has_cjk(value: str) -> bool:
    """Return True if ``value`` contains any CJK Unified Ideograph.

    Used to disambiguate Chinese display names from English symbols or
    numeric data fields in upstream quote payloads.
    """
    if not value:
        return False
    return bool(_CJK_PATTERN.search(value))


def _extract_quoted_payload(text: str) -> str | None:
    """Return the content of the first ``"..."`` group in ``text``.

    Sina and Tencent both wrap their payloads in double quotes:
        var hq_str_gb_aapl="...";
        v_usAAPL="...";
    """
    match = re.search(r'"([^"]*)"', text or "")
    if not match:
        return None
    payload = match.group(1)
    if payload is None:
        return None
    payload = payload.strip()
    return payload or None


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class EastMoneyZhProvider:
    """Fetch Chinese (or English fallback) name for a US instrument.

    Tries East Money, then Sina, then Tencent, then Yahoo — returning the
    first non-empty result.
    """

    def __init__(
        self,
        timeout: float = _TIMEOUT,
        session: requests.Session | None = None,
    ) -> None:
        self._timeout = timeout
        self._session = session or requests.Session()
        # Force a real browser User-Agent — all four upstreams occasionally
        # block the default ``python-requests/...`` agent.
        self._session.headers["User-Agent"] = _USER_AGENT
        # Cache key: (source, market_id, symbol).  Including the source
        # means one source's blank/exception doesn't poison the others.
        self._cache: dict[tuple[str, int, str], tuple[float, str | None]] = {}
        self._cache_lock = threading.Lock()

    # ---- public API ------------------------------------------------------

    def fetch_chinese_name(
        self, symbol: str, market: str = "US", exchange: str | None = None
    ) -> str | None:
        """Return the Chinese (or English-fallback) name for ``symbol``.

        ``market`` is the platform's market label (``"US"``, ``"HK"`` …) —
        only ``"US"`` is supported today; everything else returns None.

        ``exchange`` is the platform's exchange label (``"NASDAQ"``,
        ``"NYSE"`` …) and helps pick the correct East Money secid prefix.
        """
        sym = (symbol or "").strip().upper()
        if not sym:
            return None

        if (market or "").upper() != "US":
            # Future: handle HK (``secid=116``), JP, etc.
            return None

        # Phase 1 — East Money.  We try each secid prefix in turn and
        # individually cache each attempt so a 502 on one prefix doesn't
        # blank the other.
        em_name = self._try_eastmoney_chain(sym, exchange)
        if em_name:
            return em_name

        # Phase 2 — fallback chain (Sina -> Tencent -> Yahoo).
        for source, query_fn in (
            (_SOURCE_SINA, self._query_sina),
            (_SOURCE_TENCENT, self._query_tencent),
            (_SOURCE_YAHOO, self._query_yahoo),
        ):
            cached = self._get_cached(source, _NO_MARKET_ID, sym)
            if cached is not _SENTINEL_MISS:
                if cached:
                    return cached
                # Negative-cached — try the next source rather than
                # re-querying within the 5-minute window.
                continue

            try:
                name = query_fn(sym)
            except requests.RequestException as exc:  # network/timeout
                logger.warning(
                    "%s ZH lookup failed for %s: %s", source, sym, exc,
                )
                name = None
            except Exception as exc:  # noqa: BLE001 — defensive
                logger.warning(
                    "%s ZH lookup raised for %s: %s", source, sym, exc,
                )
                name = None

            self._set_cache(source, _NO_MARKET_ID, sym, name)
            if name:
                return name

        return None

    # ---- East Money -----------------------------------------------------

    def _try_eastmoney_chain(self, sym: str, exchange: str | None) -> str | None:
        """Run the East Money secid-prefix loop and return the first hit."""
        last_exc: Exception | None = None
        for market_id in _infer_us_market_id(sym, exchange):
            cached = self._get_cached(_SOURCE_EASTMONEY, market_id, sym)
            if cached is not _SENTINEL_MISS:
                if cached is None:
                    # Negative-cached for this prefix — try the next one.
                    continue
                return cached

            try:
                name = self._query_eastmoney(market_id, sym)
            except requests.RequestException as exc:  # network/timeout
                last_exc = exc
                logger.warning(
                    "East Money ZH lookup failed secid=%s symbol=%s: %s",
                    market_id, sym, exc,
                )
                name = None
            except ValueError as exc:
                # JSON parse error from a malformed or HTML response.
                last_exc = exc
                logger.warning(
                    "East Money ZH lookup returned bad JSON secid=%s symbol=%s: %s",
                    market_id, sym, exc,
                )
                name = None

            self._set_cache(_SOURCE_EASTMONEY, market_id, sym, name)
            if name:
                return name

        if last_exc is not None:
            logger.debug(
                "East Money ZH lookup exhausted for %s: %s", sym, last_exc,
            )
        return None

    def _query_eastmoney(self, market_id: int, symbol: str) -> str | None:
        """Hit the East Money endpoint once for a given (market_id, symbol)."""
        params = {
            "secid": f"{market_id}.{symbol}",
            "fields": "f57,f58,f12,f14",
        }
        resp = self._session.get(_BASE_URL, params=params, timeout=self._timeout)
        if resp.status_code >= 400:
            # Treat any non-2xx as a hard miss — common case is 502 /
            # RemoteDisconnected when the upstream rate-limits us.
            raise requests.RequestException(
                f"East Money returned HTTP {resp.status_code} for secid={market_id}"
            )
        resp.raise_for_status()
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ValueError(f"East Money returned non-JSON body: {exc}") from exc
        if not isinstance(payload, dict):
            return None
        data = payload.get("data")
        if not isinstance(data, dict):
            return None
        # f58 is the Chinese name; f57 is the symbol East Money matched.
        f57 = _clean(data.get("f57"))
        if f57 and f57.upper() != symbol.upper():
            # Different security — wrong market prefix; bail so caller tries
            # the next prefix.
            return None
        return _clean(data.get("f58"))

    # ---- Sina Finance ---------------------------------------------------

    def _query_sina(self, symbol: str) -> str | None:
        """Hit Sina Finance's HK/US quote endpoint.

        URL: ``https://hq.sinajs.cn/list=gb_{SYMBOL}``
        Response: ``var hq_str_gb_aapl="苹果,APPLE,105.AAPL,...";``
        The payload is comma-separated.  Per spec the 2nd field is the
        Chinese name, but the example shows it at position 0; we walk
        the leading fields and return the first that contains CJK
        characters (so English placeholders like "APPLE" or numeric
        prices never get mistaken for the Chinese display name).
        """
        url = f"https://hq.sinajs.cn/list=gb_{symbol.lower()}"
        headers = {"Referer": "https://finance.sina.com.cn/"}
        resp = self._session.get(
            url, headers=headers, timeout=self._timeout,
        )
        resp.raise_for_status()
        # hq.sinajs.cn frequently serves GBK without a charset header;
        # apparent_encoding picks the right codec via chardet.
        encoding = getattr(resp, "apparent_encoding", None) or resp.encoding or "utf-8"
        try:
            text = resp.content.decode(encoding, errors="replace")
        except (LookupError, TypeError):
            text = resp.text

        payload = _extract_quoted_payload(text)
        if payload is None:
            return None
        fields = payload.split(",")
        # Inspect the first five fields — beyond that the data is OHLCV
        # which never contains the name.
        for idx in range(min(5, len(fields))):
            candidate = _clean(fields[idx])
            if candidate and _has_cjk(candidate):
                return candidate
        return None

    # ---- Tencent Finance ------------------------------------------------

    def _query_tencent(self, symbol: str) -> str | None:
        """Hit Tencent Finance's US quote endpoint.

        URL: ``https://qt.gtimg.cn/q=us{SYMBOL}``
        Response: ``v_usAAPL="200~苹果~AAPL.OQ~...";`` (GBK)
        The 2nd ``~``-delimited field is the Chinese name per spec; we
        still verify it contains CJK so a shuffled payload doesn't
        bleed an English/short-code field into the cache.  When the
        symbol is unknown, the payload starts with ``pv_none_match``.
        """
        url = f"https://qt.gtimg.cn/q=us{symbol.lower()}"
        resp = self._session.get(url, timeout=self._timeout)
        resp.raise_for_status()
        # qt.gtimg.cn serves GBK; force-decode regardless of headers.
        text = resp.content.decode("gbk", errors="replace")

        payload = _extract_quoted_payload(text)
        if payload is None:
            return None
        if payload.startswith("pv_none"):
            return None
        fields = payload.split("~")
        # Walk the leading fields and return the first with CJK content.
        for idx in range(min(5, len(fields))):
            candidate = _clean(fields[idx])
            if candidate and _has_cjk(candidate):
                return candidate
        return None

    # ---- Yahoo Finance (English fallback) -------------------------------

    def _query_yahoo(self, symbol: str) -> str | None:
        """Hit Yahoo Finance's chart endpoint as a last-resort English name.

        URL: ``https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}``
        Reads ``meta.shortName`` (preferred) falling back to
        ``meta.longName``.  Returns English — we accept this only after
        every Chinese source has been exhausted.
        """
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        resp = self._session.get(url, timeout=self._timeout)
        resp.raise_for_status()
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ValueError(f"Yahoo returned non-JSON body: {exc}") from exc
        if not isinstance(payload, dict):
            return None
        chart = payload.get("chart")
        if not isinstance(chart, dict):
            return None
        results = chart.get("result")
        if not isinstance(results, list) or not results:
            return None
        first = results[0]
        if not isinstance(first, dict):
            return None
        meta = first.get("meta")
        if not isinstance(meta, dict):
            return None
        return _clean(meta.get("shortName")) or _clean(meta.get("longName"))

    # ---- cache ----------------------------------------------------------

    def _get_cached(self, source: str, market_id: int, symbol: str):
        now = time.monotonic()
        with self._cache_lock:
            entry = self._cache.get((source, market_id, symbol))
            if entry is None:
                return _SENTINEL_MISS
            expires_at, value = entry
            if expires_at < now:
                self._cache.pop((source, market_id, symbol), None)
                return _SENTINEL_MISS
            return value

    def _set_cache(
        self,
        source: str,
        market_id: int,
        symbol: str,
        value: str | None,
    ) -> None:
        ttl = _CACHE_TTL_SECONDS if value else _NEGATIVE_CACHE_TTL
        with self._cache_lock:
            self._cache[(source, market_id, symbol)] = (
                time.monotonic() + ttl,
                value,
            )


# Sentinel used internally to distinguish "no cache entry" from "cached None".
_SENTINEL_MISS = object()
