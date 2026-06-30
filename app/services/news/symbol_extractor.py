"""Symbol extraction for A-share (and US / crypto) news.

This module complements ``app.services.news.crawler.symbol_extractor``
which handles US English-language tickers. The extractor here is
designed for *Chinese* news where:

  - Stocks are usually referred to by name (e.g. 贵州茅台) rather than
    by code (e.g. 600519), with the code only sometimes present.
  - The 6-digit code, when present, lacks an exchange suffix; we
    infer SH (6xxxxx) vs SZ (0/3xxxxx) from the first digit.
  - US tickers in Chinese text often appear in their English form
    (TSLA / 苹果) or as cashtags ($TSLA).

Strategy
--------
1. Build a small name→symbol lookup from ``etf_info`` and (if
   present) the A-share stock rows, cached per-instance.
2. Scan the title for explicit codes (``600519.SH``, ``000001.SZ``,
   bare 6-digit numbers in the right ranges).
3. Scan the title + body for known names.
4. Reuse ``app.services.news.crawler.symbol_extractor.extract_symbols``
   to pick up US / cashtag matches so we don't double-implement that
   logic.

The class never raises. Returns ``[]`` when nothing matches.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.etf import ETFInfo
from app.services.news.crawler.symbol_extractor import extract_symbols

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

# Explicit A-share codes with exchange suffix: 600519.SH / 000001.SZ
_A_CODE_EXPLICIT_RE = re.compile(r"\b(\d{6})\.(SH|SZ|sh|sz|BJ|bj)\b")

# Bare 6-digit codes: we then infer the exchange from the first digit.
#   6xxxxx  → SH (Shanghai main board + ETF)
#   0/3xxxxx → SZ (Shenzhen main board + ChiNext)
#   9xxxxx  → SH B-shares
#   2xxxxx  → SH B-shares
_A_CODE_BARE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")

_US_CASHTAG_RE = re.compile(r"\$([A-Z][A-Z0-9.\-]{0,5})")


def _infer_exchange(code: str) -> str | None:
    """Map a 6-digit A-share code to its exchange.

    Returns ``"SH"`` / ``"SZ"`` / ``"BJ"`` or ``None`` if the code
    doesn't look like a recognised A-share number.
    """
    if not (len(code) == 6 and code.isdigit()):
        return None
    first = code[0]
    if first in ("6", "9"):  # SH main / SH B-shares
        return "SH"
    if first in ("0", "3"):  # SZ main / SZ ChiNext
        return "SZ"
    if first in ("4", "8"):  # BJ (Beijing exchange) — newer listings
        return "BJ"
    if first == "2":  # SH B-shares
        return "SH"
    return None


def _to_internal_a(code: str) -> str:
    """Return the internal ``600519.SH`` form for an A-share code."""
    ex = _infer_exchange(code) or "SH"
    return f"{code}.{ex}"


def _to_internal_us(ticker: str) -> str:
    """Return the internal ``TSLA.US`` form for a US ticker."""
    return f"{ticker.upper().strip().rstrip('.')}.US"


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


class SymbolExtractor:
    """Extract instrument codes from A-share (and US / crypto) news text.

    Usage::

        extractor = SymbolExtractor(db)
        symbols = extractor.extract(title="贵州茅台发布公告", body=None)
        # → [("600519.SH", "cn_a", 0.95), ...]

    The instance caches the name→symbol lookup across calls; clear the
    cache via :attr:`invalidate_cache` after the etf_info table has
    been bulk-updated.
    """

    # Stop-list of common Chinese / English short words that look like
    # possible names but are useless as filters.
    _NAME_STOPWORDS: frozenset[str] = frozenset(
        {
            "公告", "新闻", "财经", "市场", "公司", "集团", "股份", "证券",
            "投资", "基金", "货币", "指数", "上海", "深圳", "北京", "中国",
            "美国", "香港", "中国基金", "上证", "深证", "创业板", "科创板",
            "市场", "行业", "板块", "概念", "主题", "热点", "今日", "昨日",
        }
    )

    def __init__(self, db: Session) -> None:
        self.db = db
        self._name_to_symbol: dict[str, tuple[str, str]] | None = None
        self._alias_to_symbol: dict[str, tuple[str, str]] | None = None

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------
    def invalidate_cache(self) -> None:
        """Drop the name→symbol lookup. Call after bulk updates."""
        self._name_to_symbol = None
        self._alias_to_symbol = None

    def _ensure_cache(self) -> None:
        if self._name_to_symbol is not None:
            return
        names: dict[str, tuple[str, str]] = {}
        aliases: dict[str, tuple[str, str]] = {}
        try:
            rows = self.db.execute(
                select(ETFInfo.code, ETFInfo.name, ETFInfo.market).where(
                    ETFInfo.status == "active"
                )
            ).all()
        except Exception as exc:  # noqa: BLE001 - never raise from extract
            logger.warning("SymbolExtractor: etf_info load failed: %s", exc)
            self._name_to_symbol = names
            self._alias_to_symbol = aliases
            return

        for code, name, market in rows:
            if not code or not name:
                continue
            market_norm = self._normalize_market(market)
            entry = (code, market_norm)
            # Primary name. Use a case-folded, whitespace-collapsed key.
            key = self._name_key(name)
            if key and key not in names:
                names[key] = entry
            # Common 2-3 char abbreviation — Chinese ETFs are usually
            # referred to by the tail of their full name (e.g.
            # "沪深300ETF" → "沪深300", "中证500ETF" → "中证500").
            for abbrev in self._name_abbreviations(name):
                if abbrev and abbrev not in aliases:
                    aliases[abbrev] = entry
        self._name_to_symbol = names
        self._alias_to_symbol = aliases

    @staticmethod
    def _normalize_market(market: str | None) -> str:
        if not market:
            return "cn_a"
        m = market.strip().upper()
        if m in ("A股", "CN", "CN_A", "CHINA"):
            return "cn_a"
        if m in ("US", "USA"):
            return "us"
        if m in ("HK", "HONG_KONG"):
            return "hk"
        if m in ("CRYPTO",):
            return "crypto"
        return "cn_a"

    @staticmethod
    def _name_key(name: str) -> str:
        return re.sub(r"\s+", "", name).lower()

    @staticmethod
    def _name_abbreviations(name: str) -> Iterable[str]:
        """Yield short forms of a Chinese ETF name.

        Examples:
          沪深300ETF       → {"沪深300", "300ETF"}
          中证500ETF       → {"中证500", "500ETF"}
          华夏上证50ETF     → {"上证50", "50ETF"}
        """
        if not name:
            return []
        n = name.strip()
        out: list[str] = []
        # Strip trailing "ETF" / "ETF联接" etc.
        stripped = re.sub(r"(ETF联接|ETF|指数|基金)$", "", n)
        if stripped and stripped != n:
            out.append(stripped)
        # Trailing 3-digit number sequences ("300" / "500" / "50").
        for m in re.finditer(r"([一-龥]*?)(\d{2,4})", n):
            prefix, digits = m.group(1), m.group(2)
            if prefix and digits:
                out.append(f"{prefix}{digits}")
        return out

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def extract(
        self, title: str | None, body: str | None = None
    ) -> list[tuple[str, str, float]]:
        """Return ``[(symbol, market, confidence)]`` sorted by confidence.

        ``confidence`` is a rough heuristic:
          - 0.99  — explicit code (600519.SH)
          - 0.95  — A-share 6-digit bare code, exchange inferred
          - 0.85  — exact name match from etf_info
          - 0.70  — alias / abbreviation match
          - 0.60  — US cashtag (from upstream extractor)
          - 0.50  — US bare ticker (from upstream extractor)
        """
        self._ensure_cache()
        found: dict[str, tuple[str, float, str]] = {}

        title = title or ""
        body = body or ""
        haystack = f"{title}\n{body}"

        # 1) Explicit A-share codes (600519.SH etc.)
        for m in _A_CODE_EXPLICIT_RE.finditer(haystack):
            code = m.group(1)
            ex = m.group(2).upper()
            sym = f"{code}.{ex}"
            if sym not in found or found[sym][1] < 0.99:
                found[sym] = (sym, 0.99, "cn_a")

        # 2) Bare 6-digit codes — exchange inferred.
        for m in _A_CODE_BARE_RE.finditer(haystack):
            code = m.group(1)
            ex = _infer_exchange(code)
            if ex is None:
                continue
            sym = f"{code}.{ex}"
            if sym not in found or found[sym][1] < 0.95:
                found[sym] = (sym, 0.95, "cn_a")

        # 3) Name / alias match from etf_info cache.
        for source_text, confidence in ((title, 0.85), (body, 0.80)):
            if not source_text:
                continue
            for key, (sym, market) in self._iter_name_matches(source_text):
                if sym not in found or found[sym][1] < confidence:
                    found[sym] = (sym, confidence, market)

        # 4) US / cashtag matches via the upstream extractor.
        try:
            upstream = extract_symbols(haystack)
        except Exception as exc:  # noqa: BLE001
            logger.warning("upstream extract_symbols failed: %s", exc)
            upstream = set()
        for sym in upstream:
            if sym not in found:
                # Heuristic: cashtags are higher confidence than bare.
                has_cashtag = bool(_US_CASHTAG_RE.search(haystack))
                conf = 0.60 if has_cashtag else 0.50
                market = "crypto" if sym.startswith(("BTC", "ETH", "USDT", "USDC", "BNB")) else "us"
                found[sym] = (sym, conf, market)

        # Sort by confidence desc, then symbol for determinism.
        ordered = sorted(found.values(), key=lambda x: (-x[1], x[0]))
        return [(sym, market, conf) for sym, conf, market in ordered]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _iter_name_matches(
        self, text: str
    ) -> Iterable[tuple[str, tuple[str, str]]]:
        """Yield ``(key, (symbol, market))`` for every name hit in ``text``.

        The longest name wins (avoids "上证" matching when "上证50" is
        present in the cache). Names from the stopword list are skipped.
        """
        if not text or not self._name_to_symbol:
            return
        # Build the candidate list once per call — it's small.
        candidates: list[tuple[str, tuple[str, str]]] = sorted(
            self._name_to_symbol.items(), key=lambda kv: -len(kv[0])
        )
        for key, value in candidates:
            if not key or key in self._NAME_STOPWORDS:
                continue
            if key in text:
                yield key, value
        if not self._alias_to_symbol:
            return
        for key, value in sorted(
            self._alias_to_symbol.items(), key=lambda kv: -len(kv[0])
        ):
            if not key or key in self._NAME_STOPWORDS:
                continue
            if key in text:
                yield key, value
