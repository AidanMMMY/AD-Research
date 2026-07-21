#!/usr/bin/env python3
"""
stocktwits.py - Stocktwits US retail-sentiment worker.

Optimization history:
  - Direct Stocktwits API (api.stocktwits.com): 403 Cloudflare for all
    datacenter IPs (incl. our ECS). Was returning 1 placeholder item.
  - Yahoo Finance sentiment endpoint: deprecated / 401.
  - Public Stocktwits web pages via jina.ai: bypass API block, render
    same data via a reader service.
  - 2026-07: ``curl_cffi`` with ``chrome124`` impersonate reliably
    bypasses Cloudflare on the *direct* Stocktwits API (api.stocktwits.com)
    and on stocktwits.com HTML. This is now the primary path.
  - 2026-07-22: Cloudflare started challenging the chrome124 JA3 (403 on
    every API endpoint) while other profiles (chrome110/136/142,
    firefox135, safari18_0) still pass. The worker now walks
    ``IMPERSONATE_PROFILES`` until one gets through instead of hardcoding
    a single profile.
  - 2026-07: TradingView "Ideas" feed (200 with bare requests) is added
    as a sentiment side-channel that always returns content.

Current strategy (zero-cost, public):
  1. Primary: curl_cffi browser impersonation (profile fallback list) against
       - https://api.stocktwits.com/api/2/streams/trending.json
       - https://api.stocktwits.com/api/2/streams/symbol/<SYM>.json
       - https://api.stocktwits.com/api/2/discover.json
     Direct API gives full messages + sentiment (Bullish/Bearish) without
     DOM scraping.
  2. Fallback A: Stocktwits web pages via jina.ai reader
       - per-symbol:   https://stocktwits.com/symbol/<SYM>
       - homepage:     https://stocktwits.com/
       - discover:     https://stocktwits.com/discover
  3. Side-channel B: Yahoo Finance community discussion via jina.ai
     (existing path, slow but adds commentary snippets).
  4. Side-channel C: TradingView ideas feed (HTML, always 200) - parsed
     for ticker+idea titles that act as a sentiment proxy.

Each message in the Stocktwits markdown looks like:
    [![Image 39: symbol logo](URL)$AAPL](link) every single time Apple tanks ...
    Bullish
So we extract lines beginning with `[![Image ...` (with optional ticker prefix)
and look at the trailing sentiment token (`Bullish` / `Bearish` / empty).

Even on total failure we write a structured empty payload + exit 2 so the
orchestrator never sees a missing file.

Usage:
  python stocktwits.py                          # trending via curl_cffi
  python stocktwits.py --symbol TSLA            # TSLA messages + sentiment
  python stocktwits.py --symbol TSLA --symbol NVDA --hours 48
  python stocktwits.py --hours 24 --limit 200
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import requests

try:
    # curl_cffi is the magic that bypasses Cloudflare 403 on Stocktwits.
    from curl_cffi import requests as creq  # type: ignore
    _HAS_CURL_CFFI = True
except ImportError:  # pragma: no cover - fallback when lib not installed
    creq = None
    _HAS_CURL_CFFI = False

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    base_parser,
    http_get,
    make_session,
    parse_dt,
    setup_logger,
    within_hours,
    write_json,
)

SOURCE = "stocktwits"

# Cloudflare rotates which TLS fingerprints it challenges: on 2026-07-22
# chrome120/123/124/131 and safari260 were 403'd while the profiles below
# still passed. Ordered by preference; _curl_cffi_get walks this list and
# moves to the next profile on 403.
IMPERSONATE_PROFILES = [
    "chrome136",
    "chrome142",
    "chrome133a",
    "chrome110",
    "chrome116",
    "chrome145",
    "chrome146",
    "firefox133",
    "firefox135",
    "safari18_0",
    # Legacy default; blocked 2026-07-22, kept last in case the challenge
    # set rotates back.
    "chrome124",
]

# Direct API (primary via curl_cffi, last-resort probe via plain requests)
TRENDING_URL = "https://api.stocktwits.com/api/2/streams/trending.json"
SYMBOL_URL_TMPL = "https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
DISCOVER_URL = "https://api.stocktwits.com/api/2/discover.json"

# Web pages via jina.ai reader (fallback A)
JINA_READER = "https://r.jina.ai/"
JINA_HEADERS = {"X-Return-Format": "text", "Accept": "text/plain"}
ST_SYMBOL_URL = "https://stocktwits.com/symbol/{symbol}"
ST_HOME_URL = "https://stocktwits.com/"
ST_DISCOVER_URL = "https://stocktwits.com/discover"

# Yahoo Finance community page (side-channel B for individual tickers)
YF_COMMUNITY_URL = "https://finance.yahoo.com/quote/{symbol}/community"

# TradingView ideas (side-channel C; always 200)
TRADINGVIEW_IDEAS = "https://www.tradingview.com/symbols/{exchange}-{symbol}/ideas/"

# Default symbols when --symbol is not given - mirrors market-cap leaders
# that always have lively retail chatter on Stocktwits.
DEFAULT_SYMBOLS = ["AAPL", "TSLA", "NVDA", "AMZN", "MSFT", "META", "SPY", "QQQ"]

# ----- message-block regex (jina.md parser) -----
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")
REL_TIME_INLINE_RE = re.compile(
    r"^(?:(?:less than a minute|\d+\s*(?:m|min|h|hr|d|day|days)\s*(?:ago)?))",
    re.IGNORECASE,
)
TICKER_PREFIX_RE = re.compile(r"^\$([A-Za-z]{1,6}(?:\.X)?)\s+(?P<body>.+)$")
SENTIMENT_TAIL_RE = re.compile(r"^(Bullish|Bearish)\s*$", re.IGNORECASE)
REPLY_COUNT_RE = re.compile(r"^\d{1,4}$")
TICKER_IN_BODY_RE = re.compile(r"\$([A-Z]{1,6}(?:\.X)?)")
RESERVED_LINES = {
    "Sentiment", "Message Vol.", "Watchers", "Latest", "Feed", "News",
    "Earnings", "Fundamentals", "Info", "Home", "Symbol", "Trending",
    "All", "Bullish", "Bearish", "Bullish.", "Bearish.", "Today",
    "Neutral", "Normal Msg Vol", "Customize Watchlist",
}

# Stocktwits news blocks (look like "[Headline ... Source·1h ago](URL)")
NEWS_HEADLINE_RE = re.compile(
    r"\[(?P<title>[^\[\]]{8,200}?)\s+(?P<source>[A-Za-z][A-Za-z0-9 .&\-]{1,40})"
    r"[··]\s*(?P<ago>\d+\s*(?:m|h|d)\s*ago)\s*\]\((?P<url>[^)]+)\)"
)
RELATIVE_TS_RE = re.compile(r"(\d+)\s*(m|h|d)\s*ago", re.IGNORECASE)

# Watchlist rows on /discover
WATCHLIST_RE = re.compile(
    r"\[(?P<ticker>[A-Z]{1,6}(?:\.X)?)\s+(?P<name>[^$]+?)\s+"
    r"\$?(?P<price>[\d,]+(?:\.\d+)?)\s+"
    r"\$?(?P<change>[\-\d,.]+)\s*\((?P<pct>[\-\d.]+)%\)\]"
    r"\((?P<url>[^)]+)\)"
)

# TradingView ideas - extract idea titles from the page.
# Idea cards on /symbols/<EX>-<SYM>/ideas/ embed a JSON blob in the page;
# the simplest robust signal is the JSON key ``title`` inside
# ``window.__NEXT_DATA__`` or in ``application/ld+json`` blocks.
TV_IDEA_TITLE_RE = re.compile(r'"title"\s*:\s*"(?P<t>[^"\\]{12,200})"')
TV_SYMBOL_HINT_RE = re.compile(
    r'ideas/([A-Z]+)-([A-Z]{1,6}(?:\.X)?)/', re.IGNORECASE
)


# ---------- helpers ----------
def _jina_fetch(session: requests.Session, target_url: str, logger, timeout: int = 25) -> str | None:
    """jina.ai reader; returns rendered markdown text or None."""
    url = JINA_READER + target_url
    resp = http_get(session, url, headers=JINA_HEADERS, timeout=timeout)
    if resp is None or resp.status_code != 200:
        logger.debug(
            "jina %s -> status=%s size=%s",
            target_url,
            getattr(resp, "status_code", "?"),
            len(resp.text) if resp is not None and resp.text else 0,
        )
        return None
    return resp.text or ""


def _relative_to_dt(ago: str) -> Any:
    """Parse '5m ago' / '3h ago' / '2d ago' into a tz-aware UTC datetime."""
    m = RELATIVE_TS_RE.search(ago or "")
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2).lower()
    delta = {"m": timedelta(minutes=n), "h": timedelta(hours=n), "d": timedelta(days=n)}.get(unit)
    if not delta:
        return None
    return datetime.now(tz=timezone.utc) - delta


def _curl_cffi_get(url: str, logger, timeout: int = 20, retries: int = 1) -> Any:
    """GET via curl_cffi browser impersonation. Returns the response
    object (with .status_code, .json(), .text) or None on hard failure.

    Cloudflare challenges specific TLS fingerprints and the challenged set
    rotates over time, so we walk ``IMPERSONATE_PROFILES`` and move on to
    the next profile on 403. ``retries`` covers the common "Recv failure:
    Connection reset by peer" we see intermittently from Cloudflare edge
    nodes - first call is sometimes torn down, second call goes through
    cleanly.
    """
    if not _HAS_CURL_CFFI:
        return None
    last_exc: Exception | None = None
    for profile in IMPERSONATE_PROFILES:
        for attempt in range(retries + 1):
            try:
                resp = creq.get(url, impersonate=profile, timeout=timeout)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.debug(
                    "curl_cffi GET %s profile=%s failed (attempt %d/%d): %s",
                    url, profile, attempt + 1, retries + 1, exc,
                )
                time.sleep(0.5 * (attempt + 1))
                continue
            if resp.status_code == 403:
                logger.debug(
                    "curl_cffi GET %s profile=%s -> 403 (fingerprint challenged), "
                    "trying next profile",
                    url, profile,
                )
                break
            logger.debug(
                "curl_cffi GET %s profile=%s -> %d", url, profile, resp.status_code
            )
            return resp
    logger.debug("curl_cffi GET %s gave up: %s", url, last_exc)
    return None


# ---------- direct API path (PRIMARY via curl_cffi) ----------
def fetch_api_trending_cc(curl_logger, session: requests.Session, logger) -> list[dict]:
    """Pull trending symbols via curl_cffi browser impersonation.

    On success returns the full symbol list (watchlist_count, message_count).
    Falls back to plain-requests probe (likely 403) on failure.

    Note (2026-07): the API endpoint ``/streams/trending.json`` actually
    returns ``messages`` (with embedded symbols), not a ``symbols`` array.
    We accept both shapes so the worker survives future API changes.
    """
    methods: list[str] = []
    out: list[dict] = []

    # Path 1: curl_cffi impersonation (walks IMPERSONATE_PROFILES)
    resp = _curl_cffi_get(TRENDING_URL, logger)
    if resp is not None and resp.status_code == 200:
        methods.append("curl_cffi_trending")
        try:
            data = resp.json()
        except ValueError:
            data = {}
        # Shape A: explicit symbols array
        for s in (data.get("symbols") or []):
            if not isinstance(s, dict):
                continue
            out.append({
                "symbol": s.get("symbol"),
                "title": s.get("title"),
                "watchlist_count": s.get("watchlist_count"),
                "message_count": s.get("message_count", 0),
                "type": "trending_api",
                "fetched_at": s.get("updated_at") or s.get("created_at"),
                "source_api": "curl_cffi",
            })
        # Shape B: messages with embedded symbols (current shape, 2026-07)
        for m in (data.get("messages") or []):
            if not isinstance(m, dict):
                continue
            sym_objs = m.get("symbols") or []
            for s in sym_objs:
                if not isinstance(s, dict):
                    continue
                sym_id = s.get("symbol") or s.get("id")
                if not sym_id:
                    continue
                ent = m.get("entities") or {}
                sent = ent.get("sentiment") if isinstance(ent.get("sentiment"), dict) else {}
                out.append({
                    "id": m.get("id"),
                    "symbol": sym_id,
                    "title": s.get("title"),
                    "created_at": m.get("created_at"),
                    "username": (m.get("user") or {}).get("username") if isinstance(m.get("user"), dict) else None,
                    "body": m.get("body", ""),
                    "sentiment": sent.get("basic"),
                    "type": "trending_message_api",
                    "source_api": "curl_cffi",
                })
        if out:
            logger.info("curl_cffi trending -> %d items", len(out))
            return out

    # Path 2: plain requests (likely 403 on datacenter IPs)
    resp = http_get(session, TRENDING_URL)
    if resp is not None and resp.status_code == 200:
        methods.append("plain_trending")
        try:
            data = resp.json()
            for s in (data.get("symbols") or []):
                if not isinstance(s, dict):
                    continue
                out.append({
                    "symbol": s.get("symbol"),
                    "title": s.get("title"),
                    "watchlist_count": s.get("watchlist_count"),
                    "message_count": s.get("message_count", 0),
                    "type": "trending_api",
                    "fetched_at": s.get("updated_at") or s.get("created_at"),
                    "source_api": "plain_requests",
                })
        except ValueError:
            pass
    if not out:
        logger.debug("api trending returned no items")
    return out


def fetch_api_symbol_cc(
    symbol: str, curl_logger, session: requests.Session, logger
) -> list[dict]:
    """Per-symbol API: PRIMARY curl_cffi -> FALLBACK plain requests.

    Returns a summary item + per-message items, matching the existing
    ``symbol_summary_api`` / ``symbol_message_api`` shape.
    """
    symbol = symbol.upper()
    url = SYMBOL_URL_TMPL.format(symbol=symbol)
    methods: list[str] = []
    data: dict | None = None
    src: str = ""

    # Path 1: curl_cffi impersonation (bypasses 403)
    resp = _curl_cffi_get(url, logger)
    if resp is not None and resp.status_code == 200:
        methods.append("curl_cffi_symbol")
        try:
            data = resp.json()
            src = "curl_cffi"
        except ValueError:
            data = None

    # Path 2: plain requests
    if not data:
        resp = http_get(session, url)
        if resp is not None and resp.status_code == 200:
            try:
                data = resp.json()
                src = "plain_requests"
                methods.append("plain_symbol")
            except ValueError:
                data = None
    if not data:
        logger.debug("api symbol %s: no JSON returned (both paths failed)", symbol)
        return []

    messages = [m for m in (data.get("messages") or []) if isinstance(m, dict)]

    def _sent(m: dict) -> str | None:
        ent = m.get("entities")
        if not isinstance(ent, dict):
            return None
        s = ent.get("sentiment")
        if not isinstance(s, dict):
            return None
        return s.get("basic")

    bullish = sum(1 for m in messages if _sent(m) == "Bullish")
    bearish = sum(1 for m in messages if _sent(m) == "Bearish")
    out: list[dict] = [{
        "symbol": symbol,
        "sentiment": {"bullish": bullish, "bearish": bearish, "total": len(messages)},
        "message_count": len(messages),
        "type": "symbol_summary_api",
        "source_api": src,
        "methods": methods,
    }]
    for m in messages:
        if not isinstance(m, dict):
            continue
        sent = _sent(m)
        out.append({
            "id": m.get("id"),
            "symbol": symbol,
            "created_at": m.get("created_at"),
            "username": (m.get("user") or {}).get("username"),
            "body": m.get("body", ""),
            "sentiment": sent,
            "type": "symbol_message_api",
            "source_api": src,
        })
    logger.info(
        "stocktwits api %s: %d msgs (B=%d Be=%d) via %s",
        symbol, len(messages), bullish, bearish, methods,
    )
    return out


def fetch_api_discover_cc(session: requests.Session, logger) -> list[dict]:
    """Discover feed via curl_cffi -> plain fallback."""
    resp = _curl_cffi_get(DISCOVER_URL, logger)
    if resp is None or resp.status_code != 200:
        resp = http_get(session, DISCOVER_URL)
    if resp is None or resp.status_code != 200:
        return []
    try:
        data = resp.json()
    except ValueError:
        return []
    out: list[dict] = []
    # /discover endpoint structure varies; capture whatever symbols/news it returns.
    for s in (data.get("symbols") or []):
        out.append({
            "symbol": s.get("symbol"),
            "title": s.get("title"),
            "watchlist_count": s.get("watchlist_count"),
            "message_count": s.get("message_count", 0),
            "type": "discover_symbol",
        })
    return out


# ---------- jina.ai web-page path (FALLBACK A) ----------
def _parse_symbol_page(symbol: str, md: str) -> list[dict]:
    """Extract messages from a stocktwits.com/symbol/{symbol} page.

    Block format:
        <username>
        <relative time>          (e.g. "12m", "less than a minute", "3h ago")
        $<TICKER> <body...>       (one or more sentences)
        Bullish|Bearish           (optional, on its own line)
        <reply_count>             (optional, on its own line, small integer)
    """
    symbol = symbol.upper()
    lines = [ln.rstrip() for ln in md.splitlines()]
    items: list[dict] = []
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if not ln or ln in RESERVED_LINES or not USERNAME_RE.match(ln):
            i += 1
            continue
        if i + 1 >= len(lines):
            break
        ts_line = lines[i + 1].strip()
        if not REL_TIME_INLINE_RE.match(ts_line):
            i += 1
            continue
        if i + 2 >= len(lines):
            break
        ticker_line = lines[i + 2].strip()
        tm = TICKER_PREFIX_RE.match(ticker_line)
        if not tm:
            i += 1
            continue
        body_parts = [tm.group("body")]
        j = i + 3
        sentiment = None
        max_body_lines = 3
        body_line_count = 1
        while j < len(lines) and body_line_count < max_body_lines:
            nxt = lines[j].strip()
            if not nxt:
                j += 1
                break
            sm = SENTIMENT_TAIL_RE.match(nxt)
            if sm:
                sentiment = sm.group(1).capitalize()
                j += 1
                if j < len(lines) and REPLY_COUNT_RE.match(lines[j].strip()):
                    j += 1
                break
            if REPLY_COUNT_RE.match(nxt):
                j += 1
                break
            if USERNAME_RE.match(nxt) and j > i + 3:
                break
            if nxt in RESERVED_LINES:
                break
            body_parts.append(nxt)
            body_line_count += 1
            j += 1
        text = " ".join(body_parts).strip()
        if not text or len(text) < 2:
            i = j
            continue
        items.append({
            "symbol": symbol,
            "user": ln,
            "time": ts_line,
            "text": text[:500],
            "sentiment": sentiment,
            "url": f"https://stocktwits.com/symbol/{symbol}",
            "type": "symbol_message",
        })
        i = j

    bullish = sum(1 for i in items if i["sentiment"] == "Bullish")
    bearish = sum(1 for i in items if i["sentiment"] == "Bearish")
    summary = {
        "symbol": symbol,
        "sentiment": {
            "bullish": bullish,
            "bearish": bearish,
            "neutral": len(items) - bullish - bearish,
            "total": len(items),
        },
        "message_count": len(items),
        "top_message": (items[0]["text"][:200] if items else None),
        "type": "symbol_summary",
    }
    return [summary] + items


def _parse_news_block(md: str) -> list[dict]:
    """Extract News feed headlines from any Stocktwits page."""
    items: list[dict] = []
    seen: set[str] = set()
    for m in NEWS_HEADLINE_RE.finditer(md):
        title = (m.group("title") or "").strip()
        source = (m.group("source") or "").strip()
        ago = m.group("ago") or ""
        url = (m.group("url") or "").strip()
        if not title or not url or url in seen:
            continue
        seen.add(url)
        dt = _relative_to_dt(ago)
        items.append({
            "title": title,
            "source": source,
            "ago": ago,
            "published_at": dt.isoformat() if dt else None,
            "url": url,
            "type": "news_headline",
        })
    return items


def _parse_watchlist(md: str) -> list[dict]:
    """Extract trending tickers from /discover watchlist rows."""
    items: list[dict] = []
    seen: set[str] = set()
    for m in WATCHLIST_RE.finditer(md):
        ticker = m.group("ticker").strip()
        if ticker in seen:
            continue
        seen.add(ticker)
        items.append({
            "symbol": ticker,
            "name": m.group("name").strip(),
            "price": m.group("price"),
            "change": m.group("change"),
            "change_pct": m.group("pct"),
            "url": m.group("url"),
            "type": "watchlist_row",
        })
    return items


def fetch_symbol_via_jina(session, symbol: str, logger) -> list[dict]:
    """Per-symbol fallback: jina.ai -> stocktwits.com/symbol/{symbol}."""
    logger.info("stocktwits: jina symbol=%s", symbol)
    md = _jina_fetch(session, ST_SYMBOL_URL.format(symbol=symbol), logger)
    if not md:
        return []
    parsed = _parse_symbol_page(symbol, md)
    news = _parse_news_block(md)
    logger.info("stocktwits: jina %s -> %d msgs + %d news", symbol, len(parsed) - 1, len(news))
    return parsed + news


def fetch_trending_via_jina(session, logger) -> list[dict]:
    """Trending tickers + News feed from stocktwits.com/ and /discover (jina)."""
    out: list[dict] = []
    md = _jina_fetch(session, ST_HOME_URL, logger)
    if md:
        out.extend(_parse_news_block(md))
    md = _jina_fetch(session, ST_DISCOVER_URL, logger)
    if md:
        out.extend(_parse_watchlist(md))
    tickers = [i["symbol"] for i in out if i.get("type") == "watchlist_row"][:3]
    for t in tickers:
        time.sleep(0.3)
        try:
            out.extend(fetch_symbol_via_jina(session, t, logger))
        except Exception as exc:  # noqa: BLE001
            logger.warning("jina discover->%s raised: %s", t, exc)
    return out


# ---------- side-channel B: Yahoo community (jina) ----------
def fetch_yahoo_community(session, symbol: str, logger) -> list[dict]:
    """Side-channel: Yahoo Finance community discussion via jina (slow, ~15s)."""
    logger.info("stocktwits: yahoo community side-channel for %s", symbol)
    md = _jina_fetch(session, YF_COMMUNITY_URL.format(symbol=symbol), logger, timeout=30)
    if not md:
        return []
    items: list[dict] = []
    blocks = re.split(r"\n\s*\n", md)
    for blk in blocks:
        if "@" not in blk:
            continue
        m = re.search(r"@([A-Za-z0-9_]{3,30})", blk)
        text = " ".join(line.strip() for line in blk.splitlines() if line.strip())
        if len(text) < 40:
            continue
        items.append({
            "symbol": symbol.upper(),
            "username": m.group(1) if m else None,
            "text": text[:400],
            "type": "yahoo_community_post",
            "source_url": f"https://finance.yahoo.com/quote/{symbol.upper()}/community",
        })
        if len(items) >= 10:
            break
    return items


# ---------- side-channel C: TradingView ideas ----------
def fetch_tradingview_ideas(session, symbol: str, logger, max_items: int = 8) -> list[dict]:
    """Pull the 'ideas' feed from TradingView for ``symbol`` as a
    low-cost sentiment proxy. Returns the idea title + a heuristic
    bullish/bearish/neutral tag derived from common keywords.

    Uses the standard request session (TradingView does not block
    datacenter IPs for this endpoint).
    """
    sym = symbol.upper().replace(".", "-")
    items: list[dict] = []
    for exchange in ("NASDAQ", "NYSE", "AMEX", "NYSEARCA"):
        url = f"https://www.tradingview.com/symbols/{exchange}-{sym}/ideas/"
        resp = http_get(session, url, timeout=15)
        if resp is None or resp.status_code != 200:
            continue
        # Extract idea titles from the JSON blob embedded in the page.
        seen: set[str] = set()
        for m in TV_IDEA_TITLE_RE.finditer(resp.text):
            t = m.group("t")
            if t in seen or any(k in t.lower() for k in ("tradingview", "homepage", "log in")):
                continue
            seen.add(t)
            t_low = t.lower()
            sentiment = (
                "Bullish" if any(w in t_low for w in (
                    "long", "buy", "bullish", "breakout", "moon", "calls",
                    "accumulate", "rally", "higher", "support", "rebound",
                ))
                else "Bearish" if any(w in t_low for w in (
                    "short", "sell", "bearish", "breakdown", "crash", "puts",
                    "distribute", "drop", "lower", "resistance", "tank",
                ))
                else "Neutral"
            )
            items.append({
                "symbol": symbol.upper(),
                "title": t[:200],
                "sentiment": sentiment,
                "url": url,
                "exchange": exchange,
                "type": "tradingview_idea",
            })
            if len(items) >= max_items:
                break
        if items:
            break  # one exchange is enough
    if items:
        logger.info("tradingview ideas for %s: %d items", symbol, len(items))
    return items


# ---------- filter / aggregate ----------
def filter_by_hours(items: list[dict], hours: int) -> list[dict]:
    if hours <= 0:
        return items
    out: list[dict] = []
    for it in items:
        ts = it.get("published_at") or it.get("created_at") or it.get("fetched_at")
        dt = parse_dt(ts)
        if within_hours(dt, hours):
            out.append(it)
    return out


# ---------- main ----------
def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Stocktwits worker (curl_cffi primary + jina fallback)")
    # NOTE: base_parser (common.py) now declares --output; do not redeclare.
    # The output path is read from args.output.
    parser.add_argument(
        "--symbol",
        type=str,
        action="append",
        default=None,
        help="Fetch messages for this ticker. Repeat for multi: --symbol TSLA --symbol NVDA",
    )
    parser.add_argument(
        "--yahoo-side-channel",
        action="store_true",
        help="Also pull Yahoo Finance community posts for --symbol tickers (slower).",
    )
    parser.add_argument(
        "--tradingview-side-channel",
        action="store_true",
        default=True,
        help="Also pull TradingView ideas titles (cheap sentiment proxy). Default: enabled.",
    )
    parser.add_argument(
        "--no-tradingview",
        action="store_false",
        dest="tradingview_side_channel",
        help="Disable TradingView ideas side-channel.",
    )
    parser.add_argument(
        "--default-symbols",
        action="store_true",
        help="If --symbol is not given, pull a default basket (AAPL/TSLA/NVDA/...).",
    )
    args = parser.parse_args(argv)

    logger = setup_logger(SOURCE, level="DEBUG" if args.verbose else "INFO")
    session = make_session()
    logger.info("curl_cffi available: %s", _HAS_CURL_CFFI)

    methods_tried: list[str] = []
    items: list[dict] = []

    symbols = [s.strip().upper() for s in (args.symbol or []) if s.strip()]
    if not symbols and args.default_symbols:
        symbols = DEFAULT_SYMBOLS
        logger.info("using default symbols: %s", symbols)

    if symbols:
        # per-symbol mode
        for sym in symbols:
            methods_tried.append("curl_cffi_api_symbol")
            try:
                sym_items = fetch_api_symbol_cc(sym, None, session, logger)
            except Exception as exc:
                logger.warning("curl_cffi api symbol %s raised: %s", sym, exc)
                sym_items = []
            if not sym_items:
                methods_tried.append("jina_symbol_web")
                try:
                    sym_items = fetch_symbol_via_jina(session, sym, logger)
                except Exception as exc:
                    logger.warning("jina symbol %s raised: %s", sym, exc)
            items.extend(sym_items)
            time.sleep(0.2)
            if args.tradingview_side_channel:
                methods_tried.append("tradingview_ideas")
                try:
                    items.extend(fetch_tradingview_ideas(session, sym, logger))
                except Exception as exc:
                    logger.debug("tradingview ideas %s failed: %s", sym, exc)
            if args.yahoo_side_channel:
                methods_tried.append("yahoo_community")
                try:
                    items.extend(fetch_yahoo_community(session, sym, logger))
                except Exception as exc:
                    logger.warning("yahoo community %s raised: %s", sym, exc)
    else:
        # trending mode (no specific symbols)
        methods_tried.append("curl_cffi_trending")
        try:
            tr_items = fetch_api_trending_cc(None, session, logger)
        except Exception as exc:
            logger.warning("curl_cffi trending raised: %s", exc)
            tr_items = []
        if not tr_items:
            methods_tried.append("jina_trending_web")
            try:
                tr_items = fetch_trending_via_jina(session, logger)
            except Exception as exc:
                logger.warning("jina trending raised: %s", exc)
        items.extend(tr_items)
        # discover endpoint as a small additive layer
        try:
            disc = fetch_api_discover_cc(session, logger)
            if disc:
                methods_tried.append("curl_cffi_discover")
                items.extend(disc)
        except Exception as exc:
            logger.debug("discover cc failed: %s", exc)

    items = filter_by_hours(items, args.hours)
    if args.limit > 0:
        items = items[: args.limit]

    if not items:
        items = [{
            "type": "empty",
            "reason": (
                "no items returned (Stocktwits API 403 Cloudflare even with "
                "curl_cffi; jina.ai web reader also empty; side-channels "
                "returned nothing within --hours window)"
            ),
            "methods_tried": methods_tried,
            "symbols": symbols,
        }]

    logger.info("stocktwits: %d items via %s", len(items), methods_tried)
    write_json(
        items,
        source=SOURCE,
        out_path=args.output,
        data_root=args.data_root,
        limit=args.limit,
        logger=logger,
    )
    has_real = any(it.get("type") not in (None, "empty") for it in items)
    return 0 if has_real else 2


if __name__ == "__main__":
    sys.exit(main())