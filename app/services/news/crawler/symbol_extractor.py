"""Ticker / cashtag / subreddit → internal symbol extraction.

Shared by every crawler (Yahoo / CNBC / SEC / Reddit / ...) so that
downstream sentiment jobs see the same ``CODE.US`` form regardless of
upstream spelling.

Strategy:
  1. Explicit cashtags  : $TSLA → TSLA
  2. Bare uppercase tickers in title / body (1-5 letters, surrounded
     by word boundaries, filtered against a small common-words set).
  3. r/{ticker} subreddit handles, e.g. r/tesla → TSLA.
  4. A small static list maps company nicknames (e.g. "Tesla") to
     tickers when no explicit cashtag is present.

The output is a set of internal ``XXXX.US`` codes, ready to be written
to ``news_article_symbol``. The function never raises — best-effort.
"""

from __future__ import annotations

import re
from typing import Iterable

# Common English words that look like tickers but almost never are.
# 1-3 letter combinations that collide with pronouns / articles / prepositions.
_STOPWORDS = {
    "A", "I", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "HE", "IF",
    "IN", "IS", "IT", "ME", "MY", "NO", "OF", "OH", "OK", "ON", "OR", "SO",
    "TO", "UP", "US", "WE", "ALL", "AND", "ANY", "ARE", "BIG", "BUT", "CAN",
    "DID", "DO", "FOR", "GET", "GOT", "HAS", "HAD", "HER", "HIM", "HIS",
    "HOW", "ITS", "LET", "MAY", "NEW", "NOT", "NOW", "OLD", "ONE", "OUR",
    "OUT", "OWN", "PUT", "RUN", "SAY", "SET", "SHE", "THE", "TOO", "TWO",
    "USE", "WAS", "WAY", "WHO", "WHY", "YET", "YOU", "YOUR", "FROM",
    "WITH", "THIS", "THAT", "HAVE", "BEEN", "WILL", "JUST", "LIKE", "INTO",
    "OVER", "AFTER", "THAN", "WHAT", "WHEN", "THEY", "THEM", "THEN",
    "ALSO", "ONLY", "MORE", "MOST", "MUCH", "SOME", "VERY", "SUCH", "EACH",
    "BOTH", "MANY", "HIGH", "LAST", "LONG", "REAL", "STILL", "TAKE",
    "GOOD", "WELL", "EVEN", "BACK", "WORK", "MUCH", "KEEP", "NEVER",
    "EVER", "FREE", "BEST", "FULL", "ETF", "ETFS", "IPO", "GDP", "FED",
    "CEO", "CFO", "EPS", "PE", "PB", "PS", "ROE", "ROA", "USD", "CNY",
    "HKD", "JPY", "EUR", "GBP", "API", "AI", "ML", "DD", "YOLO", "IMO",
    "TLDR", "EDIT", "UPDATE", "NEWS", "RATE", "YEAR", "WEEK", "DAY",
    "TIME", "DAYS", "WEEKS", "YEARS", "PRICE", "PRICES", "STOCK", "STOCKS",
    "CUT", "RATE", "FED", "HINT", "HIKE", "BOND", "BULL", "BEAR",
    "RALLY", "RALLIES", "SURGE", "SURGES", "DIP", "DIPS", "JUMP", "JUMPS",
    "MARKET", "MARKETS", "TRADE", "TRADES", "TRADING", "BUY", "SELL",
    "LONG", "SHORT", "CALL", "PUT", "PUTS", "CALLS", "HOLD", "HOLDER",
    "HOLDERS", "SHARE", "SHARES", "OPTION", "OPTIONS",
}

# Nickname → ticker map for companies mentioned without a cashtag.
_NICKNAME_MAP = {
    "TESLA": "TSLA",
    "APPLE": "AAPL",
    "MICROSOFT": "MSFT",
    "AMAZON": "AMZN",
    "GOOGLE": "GOOGL",
    "ALPHABET": "GOOGL",
    "META": "META",
    "FACEBOOK": "META",
    "NETFLIX": "NFLX",
    "NVIDIA": "NVDA",
    "AMD": "AMD",
    "INTEL": "INTC",
    "BERKSHIRE": "BRK.B",
    "COINBASE": "COIN",
    "ROBINHOOD": "HOOD",
    "PALANTIR": "PLTR",
    "BAIDU": "BIDU",
    "ALIBABA": "BABA",
    "PDD": "PDD",
    "PDD HOLDINGS": "PDD",
    "XPENG": "XPEV",
    "LI AUTO": "LI",
    "NIO": "NIO",
    "BYD": "BYDDY",
    "JPMORGAN": "JPM",
    "GOLDMAN": "GS",
    "GOLDMAN SACHS": "GS",
    "MORGAN STANLEY": "MS",
    "WALMART": "WMT",
    "DISNEY": "DIS",
    "NIKE": "NKE",
    "COCA COLA": "KO",
    "COCA-COLA": "KO",
    "PEPSI": "PEP",
    "PEPSICO": "PEP",
    "EXXON": "XOM",
    "CHEVRON": "CVX",
}

# r/{ticker_lower} handle mapping.  Reddit per-ticker sub names are
# inconsistent, so we only handle the popular ones.
_TICKER_SUBREDDIT = {
    "tsla": "TSLA", "tesla": "TSLA",
    "aapl": "AAPL", "apple": "AAPL",
    "msft": "MSFT", "microsoft": "MSFT",
    "amzn": "AMZN", "amazon": "AMZN",
    "googl": "GOOGL", "google": "GOOGL", "alphabet": "GOOGL",
    "meta": "META", "facebook": "META",
    "nflx": "NFLX", "netflix": "NFLX",
    "nvda": "NVDA", "nvidia": "NVDA",
    "amd": "AMD",
    "intc": "INTC", "intel": "INTC",
    "coin": "COIN", "coinbase": "COIN",
    "hood": "HOOD", "robinhood": "HOOD",
    "pltr": "PLTR", "palantir": "PLTR",
    "baba": "BABA", "alibaba": "BABA",
    "nio": "NIO", "xpev": "XPEV", "li": "LI",
    "jpm": "JPM", "gs": "GS", "ms": "MS",
    "wmt": "WMT", "dis": "DIS", "nke": "NKE",
    "ko": "KO", "pep": "PEP", "xom": "XOM", "cvx": "CVX",
    "spy": "SPY", "qqq": "QQQ", "iwm": "IWM", "vti": "VTI",
    "voo": "VOO", "arkk": "ARKK", "arkg": "ARKG", "arkw": "ARKW",
    "tqqq": "TQQQ", "sqqq": "SQQQ", "upro": "UPRO", "spxu": "SPXU",
    "gld": "GLD", "slv": "SLV", "uso": "USO", "tlt": "TLT",
}

_CASHTAG_RE = re.compile(r"\$([A-Z][A-Z0-9\.\-]{0,5})")
_BARE_TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")
_SUBREDDIT_RE = re.compile(r"\br/([A-Za-z0-9_]+)", flags=re.IGNORECASE)


def _to_internal(ticker: str) -> str:
    """Normalise a raw ticker to our internal ``XXXX.US`` form."""
    t = ticker.upper().strip().rstrip(".")
    return f"{t}.US"


def extract_symbols(
    text: str | None,
    *,
    subreddit: str | None = None,
    url: str | None = None,
) -> set[str]:
    """Return a set of internal ``XXXX.US`` codes from arbitrary text.

    ``subreddit`` and ``url`` are optional Reddit-specific hints.
    The function never raises.
    """
    found: set[str] = set()
    if not text and not subreddit and not url:
        return found

    haystack = (text or "").upper()

    # 1) Cashtags — highest confidence.
    for m in _CASHTAG_RE.finditer(text or ""):
        tok = m.group(1).upper().rstrip(".")
        if tok and tok not in _STOPWORDS and len(tok) <= 5:
            found.add(_to_internal(tok))

    # 2) Bare uppercase tickers.  Only consider on the title-ish content
    #    to keep false positives low; we use a simple filter against the
    #    stopword set.
    for m in _BARE_TICKER_RE.finditer(haystack):
        tok = m.group(1)
        if tok in _STOPWORDS or len(tok) < 2:
            continue
        if not (1 <= len(tok) <= 5):
            continue
        found.add(_to_internal(tok))

    # 3) Subreddit handles.
    for src in (text, url):
        if not src:
            continue
        for m in _SUBREDDIT_RE.finditer(src):
            sub = m.group(1).lower()
            if sub in _TICKER_SUBREDDIT:
                found.add(_to_internal(_TICKER_SUBREDDIT[sub]))
    if subreddit and subreddit.lower() in _TICKER_SUBREDDIT:
        found.add(_to_internal(_TICKER_SUBREDDIT[subreddit.lower()]))

    # 4) Nickname map (lowest confidence — only used for visibility).
    for nick, ticker in _NICKNAME_MAP.items():
        # Word boundary match to avoid "AAPL" matching "APPLE" partial.
        if re.search(rf"\b{re.escape(nick)}\b", haystack):
            found.add(_to_internal(ticker))

    return found


def merge_symbols(*sets: Iterable[str] | None) -> set[str]:
    """Combine multiple symbol sets into one deduplicated set."""
    out: set[str] = set()
    for s in sets:
        if not s:
            continue
        for x in s:
            out.add(x)
    return out
