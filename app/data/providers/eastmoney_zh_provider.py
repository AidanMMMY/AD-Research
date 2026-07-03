"""East Money Chinese-name lookup provider.

Used to fetch the Chinese display name (field ``f58``) for non-CN listings
that don't already have a Chinese name in our database.

Endpoint shape:
    GET https://push2.eastmoney.com/api/qt/stock/get
        ?secid={market_id}.{SYMBOL}
        &fields=f57,f58,f12,f14

Returns:
    {"data": {"f57": "AAPL", "f58": "苹果", "f12": "105.AAPL", "f14": "Apple Inc."}}

East Money's ``secid`` market prefixes are:
    * ``105`` — NYSE / AMEX (and most other US exchanges)
    * ``106`` — NASDAQ
    * ``116`` — Hong Kong
    * ``118`` — Singapore

The mapping is *conventional*, not 100% accurate — for US symbols we'll
try one prefix and fall back to the other.  Anything else returns None.

Caching: in-process dict keyed by ``(market_id, symbol)`` for 24h to
avoid re-querying the same row during a batch backfill.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

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


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class EastMoneyZhProvider:
    """Fetch Chinese name for a foreign-market instrument via East Money."""

    def __init__(
        self,
        timeout: float = _TIMEOUT,
        session: requests.Session | None = None,
    ) -> None:
        self._timeout = timeout
        self._session = session or requests.Session()
        # Force a real browser User-Agent — East Money occasionally
        # blocks the default ``python-requests/...`` agent.
        self._session.headers["User-Agent"] = _USER_AGENT
        self._cache: dict[tuple[int, str], tuple[float, str | None]] = {}
        self._cache_lock = threading.Lock()

    # ---- public API ------------------------------------------------------

    def fetch_chinese_name(
        self, symbol: str, market: str = "US", exchange: str | None = None
    ) -> str | None:
        """Return the Chinese name for ``symbol`` or ``None`` on failure.

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

        last_exc: Exception | None = None
        for market_id in _infer_us_market_id(sym, exchange):
            cached = self._get_cached(market_id, sym)
            if cached is not _SENTINEL_MISS:
                if cached is None:
                    continue
                return cached

            try:
                name = self._query_one(market_id, sym)
            except requests.RequestException as exc:  # network/timeout
                last_exc = exc
                logger.warning(
                    "East Money ZH lookup failed secid=%s symbol=%s: %s",
                    market_id, sym, exc,
                )
                continue

            self._set_cache(market_id, sym, name)
            if name:
                return name

        if last_exc is not None:
            logger.debug("East Money ZH lookup exhausted for %s: %s", sym, last_exc)
        return None

    # ---- internals -------------------------------------------------------

    def _query_one(self, market_id: int, symbol: str) -> str | None:
        """Hit the East Money endpoint once for a given (market_id, symbol)."""
        params = {
            "secid": f"{market_id}.{symbol}",
            "fields": "f57,f58,f12,f14",
        }
        resp = self._session.get(_BASE_URL, params=params, timeout=self._timeout)
        resp.raise_for_status()
        payload = resp.json()
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

    def _get_cached(self, market_id: int, symbol: str):
        now = time.monotonic()
        with self._cache_lock:
            entry = self._cache.get((market_id, symbol))
            if entry is None:
                return _SENTINEL_MISS
            expires_at, value = entry
            if expires_at < now:
                self._cache.pop((market_id, symbol), None)
                return _SENTINEL_MISS
            return value

    def _set_cache(
        self, market_id: int, symbol: str, value: str | None
    ) -> None:
        ttl = _CACHE_TTL_SECONDS if value else _NEGATIVE_CACHE_TTL
        with self._cache_lock:
            self._cache[(market_id, symbol)] = (time.monotonic() + ttl, value)


# Sentinel used internally to distinguish "no cache entry" from "cached None".
_SENTINEL_MISS = object()