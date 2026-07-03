"""Symbol mapping helpers.

Maps plain tickers coming *in* from the outside world (``AAPL``,
``600519``) to the platform's internal code convention
(``AAPL.US`` / ``600519.SH``). This is the inverse of
:func:`app.services.news.sources.xueqiu.to_xueqiu_symbol`, which
translates internal codes *out* to Xueqiu's form.

Internal convention (Tushare / Finnhub style):
  - A-share Shanghai : ``600519.SH``
  - A-share Shenzhen : ``000001.SZ``
  - A-share Beijing  : ``430047.BJ``
  - Hong Kong        : ``00700.HK``
  - US               : ``AAPL.US``
"""

import re

# 6-digit A-share codes. First digit selects the exchange:
#   6      -> Shanghai (SH)
#   0 / 3  -> Shenzhen (SZ)
#   4 / 8  -> Beijing  (BJ, NEEQ / STAR-adjacent)
_A_SHARE_RE = re.compile(r"^\d{6}$")
# 4-5 digit codes -> Hong Kong.
_HK_RE = re.compile(r"^\d{4,5}$")
# 1-5 uppercase letters (optionally with a dot, e.g. BRK.B) -> US.
_US_RE = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")

# Valid internal market suffixes; used to short-circuit already-mapped codes.
_KNOWN_SUFFIXES = {"SH", "SZ", "BJ", "HK", "US"}


def _a_share_market(code: str) -> str:
    """Return the exchange suffix for a 6-digit A-share code."""
    head = code[0]
    if head == "6":
        return "SH"
    if head in ("4", "8"):
        return "BJ"
    # 0, 3 (and anything else) default to Shenzhen.
    return "SZ"


def internal_code(symbol: str) -> str:
    """Map an external symbol to the platform's internal code.

    Examples:
        ``AAPL``   -> ``AAPL.US``
        ``600519`` -> ``600519.SH``
        ``000001`` -> ``000001.SZ``
        ``00700``  -> ``00700.HK``
        ``AAPL.US``-> ``AAPL.US`` (already internal; returned as-is)

    Unknown / unparseable inputs are returned upper-cased and stripped so
    callers always get a stable string rather than an exception.
    """
    if not symbol or not symbol.strip():
        raise ValueError("empty symbol")

    raw = symbol.strip().upper()

    # Already carries a recognised internal suffix -> normalise and return.
    if "." in raw:
        base, _, suffix = raw.rpartition(".")
        if suffix in _KNOWN_SUFFIXES:
            return f"{base}.{suffix}"
        # A dotted US ticker like BRK.B (no market suffix) -> append .US.
        if _US_RE.match(raw):
            return f"{raw}.US"
        # Unknown suffix: leave as-is.
        return raw

    # 6 digits -> A-share (SH/SZ/BJ by leading digit).
    if _A_SHARE_RE.match(raw):
        return f"{raw}.{_a_share_market(raw)}"

    # 4-5 digits -> Hong Kong, zero-padded to 5 like the internal convention.
    if _HK_RE.match(raw):
        return f"{raw.zfill(5)}.HK"

    # 1-5 uppercase letters -> US.
    if _US_RE.match(raw):
        return f"{raw}.US"

    # Fallback: return the cleaned ticker unchanged.
    return raw
