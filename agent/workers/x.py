#!/usr/bin/env python3
"""
x.py - X / Twitter data worker.

Optimization history:
  - Adaptive Search endpoint (1.1): rate-limited, returns 0 items.
  - Direct X API endpoints: requires paid X API access (not available).
  - Public mirrors (fxtwitter / vxtwitter): single-tweet lookup only, need IDs.
  - 2026-07: added ``curl_cffi`` with ``chrome124`` impersonate to scrape
    ``x.com/<user>`` profile HTML and harvest tweet IDs that the API
    mirrors (vxtwitter > fxtwitter) then resolve. vxtwitter returns
    ``date_epoch`` so we can honour the ``--hours`` window.

Current strategy (zero-cost, public):
  1. PRIMARY: curl_cffi + chrome124 to fetch the public HTML of
       x.com/{user} for a curated list of finance / market accounts
       (DeItaone, FirstSquawk, Bloomberg, MarketWatch, realDonaldTrump,
       WhiteHouse, ...). Extract /status/<id> URLs from the rendered
       HTML; resolve each ID with vxtwitter (preferred - has date_epoch)
       and fall back to fxtwitter (engagement only).
  2. FALLBACK A: DuckDuckGo search via jina.ai reader (``site:x.com <q>``)
       - returns real X result pages with tweet URLs.
  3. FALLBACK B: jina.ai directly on ``x.com/search?q=...&f=live``
       (often 403 but resilient when DDG goes down).
  4. SIDE-CHANNEL: Yahoo Finance news (cheap, always-on) - appended as
     ``type=yfinance_news`` items so the orchestrator always sees some
     context even when all X paths fail.

Each fetched tweet is normalized into the existing canonical shape:
    { id, url, user, author_name, author_handle, text, created_at,
      created_epoch, lang, source, engagement{...}, type, source_api }

Even on total failure we write a structured empty payload + exit 2 so the
orchestrator never sees a missing file.

Usage:
  python x.py --hours 24 --query "NVDA OR TSLA" --out /data/ad-research/x/today.json
  python x.py --hours 6   --query "$AAPL earnings" --limit 30
  python x.py --hours 48  --query "Federal Reserve"  # default broad query
  python x.py --hours 24                            # default preset
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import requests

try:
    from curl_cffi import requests as creq  # type: ignore
    _HAS_CURL_CFFI = True
except ImportError:  # pragma: no cover - falls back to plain requests
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

SOURCE = "x"

# ----- public endpoints -----
JINA_READER = "https://r.jina.ai/"
JINA_HEADERS = {"X-Return-Format": "text", "Accept": "text/plain"}

# Tweet detail (single tweet -> JSON). vxtwitter includes date_epoch;
# fxtwitter is a richer engagement payload but ships date=None.
VXTWITTER = "https://api.vxtwitter.com/{user}/status/{tid}"
FXTWITTER = "https://api.fxtwitter.com/{user}/status/{tid}"

DDG = "https://duckduckgo.com/?q={q}"
DDG_HTML = "https://html.duckduckgo.com/html/?q={q}"

# Direct X HTML (used via curl_cffi to harvest tweet IDs from a public
# profile page; works without an auth_token when ``impersonate`` gives
# us a real Chrome TLS fingerprint).
X_PROFILE_URL = "https://x.com/{user}"

# Side-channel: Yahoo Finance news search (always 200).
YFINANCE_NEWS = "https://finance.yahoo.com/news/"

# Match either `x.com/user/status/<id>` or `twitter.com/user/status/<id>`
# in any rendered HTML / Markdown.
TWEET_RE = re.compile(
    r"(?:x\.com|twitter\.com)/([A-Za-z0-9_]{1,30})/status/(\d{6,25})"
)

# Curated list of finance / market accounts. These are the public X
# profiles whose HTML is reachable via curl_cffi impersonate and which
# reliably publish finance / macro / market-moving content. Add/remove
# freely; the worker de-dupes IDs across accounts so overlap is cheap.
# Kept short on purpose: each profile fetch is ~5-10s from a typical
# datacenter IP and we want the layer to complete inside ~60s.
FINANCE_ACCOUNTS = [
    "DeItaone",          # Walter Bloomberg - fast headline news (most prolific)
    "FirstSquawk",       # breaking financial news (fast)
    "Bloomberg",         # Bloomberg main
    "Reuters",           # Reuters main
    "MarketWatch",       # MarketWatch
    "business",          # Bloomberg Business
    "realDonaldTrump",   # market mover on macro days
    "elonmusk",          # TSLA / DOGE / market mover
    "federalreserve",    # Fed official (low frequency but important)
    "GoldmanSachs",      # Goldman Sachs official
]

# Default preset: broad finance / market queries if --query not provided.
DEFAULT_QUERIES = [
    "NVDA",
    "TSLA",
    "AAPL",
    "Federal Reserve",
    "stock market",
]


# ====================================================================
# low-level helpers
# ====================================================================
def _jina_fetch(session: requests.Session, target_url: str, logger, timeout: int = 30) -> str | None:
    """Call jina.ai reader; returns rendered markdown or None."""
    url = JINA_READER + target_url
    resp = http_get(session, url, headers=JINA_HEADERS, timeout=timeout)
    if resp is None or resp.status_code != 200:
        logger.debug("jina %s -> status=%s", target_url, getattr(resp, "status_code", "?"))
        return None
    return resp.text or ""


def _curl_cffi_get(url: str, logger, timeout: int = 20, retries: int = 2) -> Any:
    """GET via curl_cffi chrome124 impersonate. Returns the response
    object or None on hard failure. Two retries to absorb the
    occasional ``Recv failure: Connection reset by peer`` we see on
    Cloudflare edge nodes.
    """
    if not _HAS_CURL_CFFI:
        return None
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return creq.get(url, impersonate="chrome124", timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.debug(
                "curl_cffi GET %s attempt %d/%d failed: %s",
                url, attempt + 1, retries + 1, exc,
            )
            time.sleep(0.3 * (attempt + 1))
    logger.debug("curl_cffi GET %s gave up: %s", url, last_exc)
    return None


def _ddg_search_jina(session: requests.Session, query: str, logger) -> str | None:
    """DuckDuckGo search via jina.ai reader. Adds `site:x.com` prefix."""
    q = f"site:x.com {query}"
    encoded = quote_plus(q)
    md = _jina_fetch(session, DDG_HTML.format(q=encoded), logger)
    if md and len(md) > 200:
        return md
    return _jina_fetch(session, DDG.format(q=encoded), logger)


def _extract_tweet_ids(md: str, limit: int = 30) -> list[tuple[str, str]]:
    """Find (user, tweet_id) pairs in any rendered text. Deduped, order preserved."""
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for m in TWEET_RE.finditer(md):
        user = m.group(1)
        tid = m.group(2)
        key = (user, tid)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
        if len(out) >= limit:
            break
    return out


def _fetch_tweet_detail(
    session: requests.Session,
    user: str,
    tid: str,
    logger,
    prefer_curl_cffi: bool = False,
) -> tuple[dict | None, str]:
    """Fetch full tweet JSON via vxtwitter first (has date), fxtwitter fallback."""
    # Try vxtwitter first - it returns date_epoch so we can honour --hours.
    for tmpl in (VXTWITTER, FXTWITTER):
        url = tmpl.format(user=user, tid=tid)
        resp = None
        # curl_cffi first if requested (vxtwitter/fxtwitter usually 200 plain)
        if prefer_curl_cffi:
            resp = _curl_cffi_get(url, logger, timeout=15)
        if resp is None:
            resp = http_get(session, url, timeout=15)
        if resp is None or resp.status_code != 200:
            continue
        try:
            data = resp.json()
        except ValueError:
            continue
        # vxtwitter flat shape
        if "tweetID" in data and "text" in data:
            return data, "vxtwitter"
        # fxtwitter wrapped shape
        if "tweet" in data and data["tweet"]:
            return data["tweet"], "fxtwitter"
    logger.debug("tweet %s/%s lookup failed (vxtwitter + fxtwitter)", user, tid)
    return None, ""


def _normalize_tweet(user: str, tid: str, raw: dict, source_api: str) -> dict:
    """Flatten vxtwitter / fxtwitter response into our canonical item shape."""
    if source_api == "vxtwitter":
        text = raw.get("text", "")
        author_name = user
        author_name_disp = user
        likes = raw.get("likes")
        retweets = raw.get("retweets")
        replies = raw.get("replies")
        quotes = raw.get("quotes")
        views = raw.get("views")
        created_at = raw.get("date")
        created_epoch = raw.get("date_epoch")
        url = raw.get("url") or f"https://x.com/{user}/status/{tid}"
        lang = raw.get("lang")
        source = raw.get("source")
        user_obj = raw.get("user") or {}
        if isinstance(user_obj, dict):
            author_name = user_obj.get("username") or user
            author_name_disp = user_obj.get("name") or user
    else:  # fxtwitter
        text = (
            raw.get("text")
            or (raw.get("raw_text", {}).get("text") if isinstance(raw.get("raw_text"), dict) else None)
            or (raw.get("raw_text") if not isinstance(raw.get("raw_text"), dict) else None)
            or ""
        )
        author = raw.get("author") or {}
        if isinstance(author, dict):
            author_name = author.get("screen_name") or author.get("name") or user
            author_name_disp = author.get("name") or user
        else:
            author_name = user
            author_name_disp = user
        likes = raw.get("likes") or raw.get("favorite_count")
        retweets = raw.get("retweets") or raw.get("retweet_count")
        replies = raw.get("replies") or raw.get("reply_count")
        quotes = raw.get("quotes")
        views = raw.get("views")
        created_at = raw.get("created_at") or raw.get("date")
        created_epoch = raw.get("created_timestamp") or raw.get("date_epoch")
        url = raw.get("url") or f"https://x.com/{user}/status/{tid}"
        lang = raw.get("lang")
        source = raw.get("source")
    return {
        "id": tid,
        "url": url,
        "user": user,
        "author_name": author_name_disp,
        "author_handle": author_name,
        "text": (text or "").strip(),
        "created_at": created_at,
        "created_epoch": created_epoch,
        "lang": lang,
        "source": source,
        "engagement": {
            "likes": likes,
            "retweets": retweets,
            "replies": replies,
            "quotes": quotes,
            "views": views,
        },
        "type": "tweet",
        "source_api": source_api,
    }


def _parse_ddg_inline_tweets(md: str) -> list[dict]:
    """Best-effort backstop: when tweet IDs found but fxtwitter/vxtwitter
    lookup later fails, extract inline text snippets from DDG markdown."""
    items: list[dict] = []
    for m in TWEET_RE.finditer(md):
        user = m.group(1)
        tid = m.group(2)
        start = m.end()
        snippet = md[start : start + 600]
        snippet = re.split(r"\n\s*\n|x\.com\n|twitter\.com\n", snippet, maxsplit=1)[0]
        snippet = snippet.strip().lstrip(":›-").strip()
        if not snippet:
            continue
        items.append(
            {
                "id": tid,
                "url": f"https://x.com/{user}/status/{tid}",
                "user": user,
                "text": snippet[:500],
                "created_at": None,
                "engagement": {},
                "type": "tweet_inline",
                "source_api": "ddg_inline",
            }
        )
    return items


# ====================================================================
# Layer 1 - PRIMARY: curl_cffi + x.com/{user}
# ====================================================================
def fetch_via_x_profiles(
    session: requests.Session,
    logger,
    accounts: list[str] | None = None,
    per_account_limit: int = 16,
    profile_timeout: int = 10,
) -> list[dict]:
    """Scrape ``x.com/<user>`` via curl_cffi for a curated list of finance
    accounts. Returns normalized tweets (via vxtwitter).

    The x.com HTML pages embed /status/<id> URLs even for non-logged-in
    visitors (Twitter publishes them for SEO). We harvest the unique IDs
    and resolve each one via vxtwitter (preferred - has date_epoch).

    Time-boxing: we give each profile fetch only ``profile_timeout``
    seconds (default 10s) because x.com occasionally hangs from
    Cloudflare edge nodes. The whole layer is also capped by the number
    of accounts in ``accounts``.
    """
    accounts = accounts or FINANCE_ACCOUNTS
    if not _HAS_CURL_CFFI:
        logger.debug("curl_cffi unavailable - skipping x.com profile harvest")
        return []

    all_ids: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    failed_accounts: list[str] = []

    for acct in accounts:
        url = X_PROFILE_URL.format(user=acct)
        resp = _curl_cffi_get(url, logger, timeout=profile_timeout, retries=0)
        if resp is None or resp.status_code != 200:
            failed_accounts.append(acct)
            logger.debug("x.com/%s -> status=%s", acct, getattr(resp, "status_code", "?"))
            continue
        ids = _extract_tweet_ids(resp.text, limit=per_account_limit)
        new_count = 0
        for user, tid in ids:
            if tid in seen_ids:
                continue
            seen_ids.add(tid)
            all_ids.append((user, tid))
            new_count += 1
        logger.info("x.com/%s -> %d new tweet IDs (total so far %d)", acct, new_count, len(all_ids))

    if failed_accounts:
        logger.info(
            "X primary path: %d accounts unreachable (%s)",
            len(failed_accounts), ",".join(failed_accounts[:5]),
        )
    logger.info("X primary path: harvested %d unique tweet IDs from %d accounts",
                len(all_ids), len(accounts))
    if not all_ids:
        return []

    items: list[dict] = []
    for user, tid in all_ids:
        raw, src = _fetch_tweet_detail(session, user, tid, logger, prefer_curl_cffi=False)
        if raw is None:
            continue
        items.append(_normalize_tweet(user, tid, raw, src))
    logger.info("X primary path: resolved %d tweets via vxtwitter/fxtwitter", len(items))
    return items


# ====================================================================
# Layer 2 - FALLBACK A: jina.ai + DDG (existing, kept for resilience)
# ====================================================================
def fetch_via_ddg_jina(session, query: str, logger, per_query_limit: int = 20) -> list[dict]:
    """End-to-end: jina+DDG -> tweet IDs -> vxtwitter/fxtwitter detail."""
    logger.info("X fetch: query=%r via jina+DDG", query)
    md = _ddg_search_jina(session, query, logger)
    if not md:
        logger.warning("X fetch: jina+DDG returned empty for query=%r", query)
        return []
    tweet_ids = _extract_tweet_ids(md, limit=per_query_limit)
    logger.info("X fetch: extracted %d tweet ids from DDG markdown", len(tweet_ids))
    if not tweet_ids:
        return _parse_ddg_inline_tweets(md)[:per_query_limit]
    items: list[dict] = []
    for user, tid in tweet_ids:
        time.sleep(0.25)
        raw, src = _fetch_tweet_detail(session, user, tid, logger)
        if raw is None:
            continue
        items.append(_normalize_tweet(user, tid, raw, src))
    if len(items) < len(tweet_ids) // 2:
        inline = _parse_ddg_inline_tweets(md)
        seen_ids = {i["id"] for i in items}
        for it in inline:
            if it["id"] not in seen_ids:
                items.append(it)
    return items


def fetch_via_jina_direct(session, query: str, logger) -> list[dict]:
    """Fallback: ask jina.ai directly for x.com search page."""
    logger.info("X fetch: trying jina direct x.com fallback for query=%r", query)
    target = f"https://x.com/search?q={quote_plus(query)}&f=live"
    md = _jina_fetch(session, target, logger)
    if not md:
        return []
    tweet_ids = _extract_tweet_ids(md, limit=20)
    items: list[dict] = []
    for user, tid in tweet_ids:
        raw, src = _fetch_tweet_detail(session, user, tid, logger)
        if raw:
            items.append(_normalize_tweet(user, tid, raw, src))
    return items


# ====================================================================
# Layer 4 - SIDE-CHANNEL: Yahoo Finance news (always-on, low cost)
# ====================================================================
def fetch_yfinance_news(session, query: str, logger, limit: int = 8) -> list[dict]:
    """Side-channel: pull Yahoo Finance news titles via jina.ai. Cheap
    (~2s per query) and almost always 200. Acts as a fallback context
    even when all X paths fail.
    """
    md = _jina_fetch(session, YFINANCE_NEWS, logger, timeout=20)
    if not md:
        return []
    items: list[dict] = []
    # Headline pattern in yfinance markdown:
    #   "[Some title here](https://finance.yahoo.com/news/...)"
    pattern = re.compile(r"\[(?P<title>[^\[\]]{15,200}?)\]\((?P<url>https://finance\.yahoo\.com/news/[^\)]+)\)")
    seen: set[str] = set()
    for m in pattern.finditer(md):
        title = m.group("title").strip()
        url = m.group("url").strip()
        if not title or url in seen or "yahoo.com" not in url:
            continue
        # Only keep headlines that mention any of the query tokens, when a
        # query is given. Otherwise keep the first `limit` headlines.
        if query and not any(tok.lower() in title.lower() for tok in query.split()):
            continue
        seen.add(url)
        items.append({
            "title": title,
            "url": url,
            "source": "yahoo_finance",
            "type": "yfinance_news",
        })
        if len(items) >= limit:
            break
    if items:
        logger.info("X side-channel yfinance: %d items for query=%r", len(items), query)
    return items


# ====================================================================
# collect / filter / main
# ====================================================================
def collect(
    session: requests.Session,
    queries: list[str],
    logger,
    accounts: list[str] | None = None,
    limit_per_query: int = 15,
) -> list[dict]:
    """Run all enabled layers and de-dupe the result by tweet ID."""
    all_items: list[dict] = []
    seen_ids: set[str] = set()
    methods_tried: list[str] = []

    # Layer 1: curl_cffi + x.com profiles (PRIMARY - no query dependence)
    try:
        primary = fetch_via_x_profiles(session, logger, accounts=accounts)
    except Exception as exc:  # noqa: BLE001
        logger.warning("x.com profile path raised: %s", exc)
        primary = []
    if "x_profiles" not in methods_tried and (_HAS_CURL_CFFI or primary):
        methods_tried.append("x_profiles")
    for it in primary:
        tid = it.get("id")
        if not tid or tid in seen_ids:
            continue
        seen_ids.add(tid)
        all_items.append(it)

    # Layer 2 + 3: jina.ai + DDG / direct x.com (existing, per query)
    for q in queries:
        try:
            items = fetch_via_ddg_jina(session, q, logger, per_query_limit=limit_per_query)
        except Exception as exc:
            logger.warning("DDG+jina path raised for %r: %s", q, exc)
            items = []
        if "ddg_jina" not in methods_tried:
            methods_tried.append("ddg_jina")
        if not items:
            try:
                items = fetch_via_jina_direct(session, q, logger)
            except Exception as exc:
                logger.warning("jina direct path raised for %r: %s", q, exc)
                items = []
            if "jina_direct" not in methods_tried:
                methods_tried.append("jina_direct")

        for it in items:
            tid = it.get("id")
            if not tid or tid in seen_ids:
                continue
            seen_ids.add(tid)
            all_items.append(it)

    # Layer 4: yfinance side-channel (cheap, no de-dupe needed)
    for q in queries[:3]:
        try:
            yf = fetch_yfinance_news(session, q, logger, limit=4)
        except Exception as exc:
            logger.debug("yfinance side-channel raised for %r: %s", q, exc)
            yf = []
        if yf and "yfinance" not in methods_tried:
            methods_tried.append("yfinance")
        all_items.extend(yf)

    logger.info("X collect: %d unique items via %s", len(all_items), methods_tried)
    return all_items


def filter_by_hours(items: list[dict], hours: int) -> list[dict]:
    """Apply --hours window.

    Tweets without a usable timestamp are *kept* (we don't want to throw
    away freshly-resolved vxtwitter/fxtwitter rows that lack a created_at);
    they're just un-scored by the window filter. ``yfinance_news`` and
    ``tweet_inline`` rows fall in this category too.
    """
    if hours <= 0:
        return items
    out: list[dict] = []
    for it in items:
        ts = it.get("created_epoch") or it.get("created_at") or it.get("published_at")
        dt = None
        if isinstance(ts, (int, float)):
            try:
                dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                dt = None
        if dt is None:
            dt = parse_dt(it.get("created_at") or it.get("published_at"))
        # Items without any timestamp: keep them only when type suggests
        # they were just resolved (otherwise they could be ancient).
        if dt is None:
            if it.get("type") in ("tweet", "yfinance_news"):
                out.append(it)  # unknown age -> keep; orchestrator can drop
            continue
        if within_hours(dt, hours):
            out.append(it)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("X / Twitter worker (curl_cffi primary + jina fallback + yfinance side-channel)")
    # NOTE: base_parser (common.py) now declares --output; do not redeclare.
    # The output path is read from args.output.
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Search query (e.g. 'NVDA earnings'). Repeat for multi: --query A --query B",
    )
    parser.add_argument(
        "--preset",
        choices=["finance", "macro", "crypto", "all", "none"],
        default="finance",
        help="Built-in query bundle. Default 'finance' covers NVDA/TSLA/AAPL/Fed/market.",
    )
    parser.add_argument(
        "--accounts",
        type=str,
        default=None,
        help="Comma-separated X account list to scrape. Default: built-in FINANCE_ACCOUNTS.",
    )
    parser.add_argument(
        "--no-x-profiles",
        action="store_true",
        help="Disable the curl_cffi + x.com profile primary path (e.g. on machines without curl_cffi).",
    )
    parser.add_argument(
        "--no-yfinance",
        action="store_true",
        help="Disable the Yahoo Finance side-channel.",
    )
    args = parser.parse_args(argv)

    logger = setup_logger(SOURCE, level="DEBUG" if args.verbose else "INFO")
    session = make_session()
    logger.info("curl_cffi available: %s", _HAS_CURL_CFFI)

    queries: list[str] = []
    if args.query:
        queries.extend([q.strip() for q in args.query.split(",") if q.strip()])
    if args.preset == "finance":
        queries.extend(["NVDA", "TSLA", "AAPL", "Federal Reserve", "stock market"])
    elif args.preset == "macro":
        queries.extend(["Federal Reserve", "ECB", "inflation", "Treasury yields"])
    elif args.preset == "crypto":
        queries.extend(["Bitcoin", "Ethereum", "crypto news"])
    elif args.preset == "all":
        queries.extend(["NVDA", "TSLA", "Federal Reserve", "Bitcoin"])
    if not queries:
        queries = DEFAULT_QUERIES

    accounts = None
    if args.accounts:
        accounts = [a.strip().lstrip("@") for a in args.accounts.split(",") if a.strip()]

    # Honour the disable flags by passing empty accounts / clearing the side-channel
    if args.no_x_profiles or not _HAS_CURL_CFFI:
        accounts = []  # empty -> primary layer returns []

    items = collect(
        session,
        queries,
        logger,
        accounts=accounts,
        limit_per_query=15,
    )

    # Drop yfinance side-channel if disabled
    if args.no_yfinance:
        items = [it for it in items if it.get("type") != "yfinance_news"]

    items = filter_by_hours(items, args.hours)
    if args.limit > 0:
        items = items[: args.limit]

    if not items:
        items = [{
            "type": "empty",
            "reason": (
                "no X items returned (curl_cffi + x.com profile harvest "
                "returned 0; jina.ai + DuckDuckGo search returned 0 tweet "
                "URLs; vxtwitter / fxtwitter detail lookups all failed; "
                "yfinance side-channel also empty)"
            ),
            "queries_attempted": queries,
        }]

    write_json(
        items,
        source=SOURCE,
        out_path=args.output,
        data_root=args.data_root,
        limit=args.limit,
        logger=logger,
    )
    has_real_items = any(it.get("type") not in (None, "empty") for it in items)
    return 0 if has_real_items else 2


if __name__ == "__main__":
    sys.exit(main())