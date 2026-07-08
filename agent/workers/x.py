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
  - 2026-07-08: aggressive fixes for ECS environment:
      * derive ``created_epoch`` from any tweet snowflake ID so items are not
        silently dropped by ``filter_by_hours``;
      * parse inline timestamps/text from DuckDuckGo+jina markdown as a
        primary, fast, zero-extra-call source of recent tweets;
      * resolve mirror details in parallel with a 5 s timeout;
      * expand tweet-ID regex to match relative ``/user/status/id`` links
        embedded in x.com HTML.

Current strategy (zero-cost, public):
  1. PRIMARY: DuckDuckGo search via jina.ai reader (``site:x.com <q>``).
     The markdown includes tweet URLs, inline text, and a date/time. We
     extract those and derive ``created_epoch`` from the snowflake ID, so
     even when mirror detail APIs are unavailable the worker still produces
     recent items with text and timestamps.
  2. SECONDARY: x.com/{user} profile scrape via curl_cffi. We harvest
     ``/user/status/id`` links and resolve a small number of the most
     recent IDs through fxtwitter/vxtwitter in parallel.
  3. FALLBACK: jina.ai directly on ``x.com/search?q=...&f=live``.
  4. SIDE-CHANNEL: Yahoo Finance news (cheap, always-on) - appended as
     ``type=yfinance_news`` items.

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
import concurrent.futures
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

# Twitter snowflake epoch (2010-11-04 01:42:54.657 UTC)
TWITTER_EPOCH_MS = 1288834974657

# ----- session used for fast, no-retry mirror calls -----
_FAST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

def _http_get_fast(url: str, timeout: int = 5) -> requests.Response | None:
    """Single-shot GET with no retries. Used for mirror APIs so a slow/429
    host does not compound the per-request timeout across adapter retries.
    """
    try:
        return requests.get(url, headers=_FAST_HEADERS, timeout=timeout)
    except requests.RequestException:
        return None
JINA_READER = "https://r.jina.ai/"
JINA_HEADERS = {"X-Return-Format": "text", "Accept": "text/plain"}

# Tweet detail (single tweet -> JSON). vxtwitter includes date_epoch;
# fxtwitter is a richer engagement payload but ships date=None.
VXTWITTER = "https://api.vxtwitter.com/{user}/status/{tid}"
FXTWITTER = "https://api.fxtwitter.com/{user}/status/{tid}"

DDG = "https://duckduckgo.com/?q={q}&df=d"
DDG_HTML = "https://html.duckduckgo.com/html/?q={q}&df=d"

# Direct X HTML (used via curl_cffi to harvest tweet IDs from a public
# profile page; works without an auth_token when ``impersonate`` gives
# us a real Chrome TLS fingerprint).
X_PROFILE_URL = "https://x.com/{user}"

# Side-channel: Yahoo Finance news search (always 200).
YFINANCE_NEWS = "https://finance.yahoo.com/news/"

# Match either absolute `x.com/user/status/<id>` / `twitter.com/...` or
# relative `/user/status/<id>` links found in x.com profile HTML.
TWEET_RE = re.compile(
    r"(?:^|[^/])"                       # not immediately preceded by another slash
    r"(?:x\.com|twitter\.com)?"        # optional absolute domain
    r"/([A-Za-z0-9_]{1,30})/status/(\d{6,25})"
)

# DDG markdown often places a timestamp right after the URL line:
#   x.com/itsmichaelluu/status/2061405433223344192      2026-06-01T00:00:00.0000000
DDG_TIME_RE = re.compile(
    r"(?:x\.com|twitter\.com)/([A-Za-z0-9_]{1,30})/status/(\d{6,25})\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)"
)

# Curated list of finance / market accounts. These are the public X
# profiles whose HTML is reachable via curl_cffi impersonate and which
# reliably publish finance / macro / market-moving content. We keep the
# list short because profile HTML is heavy and the primary signal now
# comes from DDG+jina.
FINANCE_ACCOUNTS = [
    "DeItaone",          # Walter Bloomberg - fast headline news
    "FirstSquawk",       # breaking financial news
    "Bloomberg",         # Bloomberg main
    "Reuters",           # Reuters main
    "MarketWatch",       # MarketWatch
    "business",          # Bloomberg Business
    "realDonaldTrump",   # market mover on macro days
    "elonmusk",          # TSLA / DOGE / market mover
    "federalreserve",    # Fed official
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
def _snowflake_to_epoch_ms(tid: str | int) -> int | None:
    """Convert a Twitter/X snowflake ID to a millisecond timestamp.

    Returns None if the ID is not a valid snowflake.
    """
    try:
        snow = int(tid)
    except (TypeError, ValueError):
        return None
    if snow <= 0:
        return None
    # Top 41 bits are ms since Twitter epoch
    return (snow >> 22) + TWITTER_EPOCH_MS


def _snowflake_to_epoch(tid: str | int) -> int | None:
    """Convert a Twitter/X snowflake ID to a Unix epoch (seconds)."""
    ms = _snowflake_to_epoch_ms(tid)
    if ms is None:
        return None
    return ms // 1000


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


def _extract_inline_tweets(md: str, limit: int = 30) -> list[dict]:
    """Best-effort extraction of inline tweet text + timestamps from DDG markdown.

    When mirror detail APIs are slow or blocked, the jina+DDG markdown already
    contains the tweet text and a timestamp. We extract that, derive a
    ``created_epoch`` from the tweet snowflake ID, and return canonical
    ``type="tweet"`` items with ``source_api="ddg_inline"``.
    """
    items: list[dict] = []
    seen: set[str] = set()
    # First pass: capture timestamps that appear right after the URL line.
    for m in DDG_TIME_RE.finditer(md):
        user, tid, ts_str = m.groups()
        if tid in seen:
            continue
        seen.add(tid)
        dt = parse_dt(ts_str)
        created_epoch = _snowflake_to_epoch(tid)
        # Snippet is the text after the timestamp line until the next blank line
        start = m.end()
        snippet = md[start : start + 600]
        snippet = re.split(r"\n\s*\n", snippet, maxsplit=1)[0]
        snippet = snippet.strip().lstrip(":›-").strip()
        items.append({
            "id": tid,
            "url": f"https://x.com/{user}/status/{tid}",
            "user": user,
            "author_name": user,
            "author_handle": user,
            "text": snippet[:500] if snippet else "",
            "created_at": ts_str if dt else None,
            "created_epoch": created_epoch,
            "lang": None,
            "source": None,
            "engagement": {},
            "type": "tweet",
            "source_api": "ddg_inline",
        })
        if len(items) >= limit:
            break

    # Second pass: any remaining tweet URLs with no timestamp, just grab nearby text
    # and derive the epoch from the snowflake ID.
    for m in TWEET_RE.finditer(md):
        user = m.group(1)
        tid = m.group(2)
        if tid in seen:
            continue
        seen.add(tid)
        start = m.end()
        snippet = md[start : start + 600]
        snippet = re.split(r"\n\s*\n|x\.com\n|twitter\.com\n", snippet, maxsplit=1)[0]
        snippet = snippet.strip().lstrip(":›-").strip()
        items.append({
            "id": tid,
            "url": f"https://x.com/{user}/status/{tid}",
            "user": user,
            "author_name": user,
            "author_handle": user,
            "text": snippet[:500] if snippet else "",
            "created_at": None,
            "created_epoch": _snowflake_to_epoch(tid),
            "lang": None,
            "source": None,
            "engagement": {},
            "type": "tweet",
            "source_api": "ddg_inline",
        })
        if len(items) >= limit:
            break
    return items


def _fetch_tweet_detail_single(
    url: str,
    label: str,
    logger,
    timeout: int = 5,
) -> tuple[dict | None, str]:
    """Fetch one mirror endpoint and return (raw, label) if it looks valid."""
    resp = _http_get_fast(url, timeout=timeout)
    if resp is None or resp.status_code != 200:
        return None, ""
    try:
        data = resp.json()
    except ValueError:
        return None, ""
    if label == "vxtwitter" and "tweetID" in data and "text" in data:
        return data, "vxtwitter"
    if label == "fxtwitter" and "tweet" in data and data["tweet"]:
        return data["tweet"], "fxtwitter"
    return None, ""


def _fetch_tweet_detail(
    session: requests.Session,
    user: str,
    tid: str,
    logger,
) -> tuple[dict | None, str]:
    """Fetch full tweet JSON via vxtwitter and fxtwitter in parallel.

    Both endpoints are queried concurrently with a short timeout so that one
    slow/429 mirror does not dominate the call. The first successful mirror
    wins. The executor is shut down without waiting for stragglers to avoid
    hanging on an unresponsive mirror.
    """
    urls = [
        (VXTWITTER.format(user=user, tid=tid), "vxtwitter"),
        (FXTWITTER.format(user=user, tid=tid), "fxtwitter"),
    ]
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    try:
        futures = [
            pool.submit(_fetch_tweet_detail_single, url, label, logger, 5)
            for url, label in urls
        ]
        done, _ = concurrent.futures.wait(
            futures, timeout=6, return_when=concurrent.futures.FIRST_COMPLETED
        )
        for fut in done:
            raw, src = fut.result()
            if raw is not None:
                return raw, src
        # No winner in the first-completed window; collect whatever is already done
        for fut in futures:
            if fut.done():
                raw, src = fut.result()
                if raw is not None:
                    return raw, src
    finally:
        pool.shutdown(wait=False)
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

    # Fallback: derive timestamp from the snowflake ID if the mirror did not
    # provide a usable date. This is the safety net that keeps ``filter_by_hours``
    # from dropping real, recent tweets.
    if created_epoch is None:
        created_epoch = _snowflake_to_epoch(tid)
    if created_at is None and created_epoch is not None:
        created_at = datetime.fromtimestamp(created_epoch, tz=timezone.utc).isoformat()

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


# ====================================================================
# Layer 1 - PRIMARY: jina.ai + DDG (fast, recent, no extra mirror calls)
# ====================================================================
def fetch_via_ddg_jina(session, query: str, logger, per_query_limit: int = 8) -> list[dict]:
    """End-to-end: jina+DDG -> inline tweet text + snowflake timestamps.

    We always extract the inline tweet data from the DDG markdown first (this is
    free once the search result is in hand). Then we try to enrich the first few
    items with mirror detail APIs in parallel, but if mirrors fail or time out
    the inline items still have text and a derived timestamp.
    """
    logger.info("X fetch: query=%r via jina+DDG", query)
    md = _ddg_search_jina(session, query, logger)
    if not md:
        logger.warning("X fetch: jina+DDG returned empty for query=%r", query)
        return []

    inline_items = _extract_inline_tweets(md, limit=per_query_limit)
    logger.info("X fetch: extracted %d inline tweets from DDG markdown", len(inline_items))
    if not inline_items:
        return []

    # Try to enrich the first N inline items with mirror details in parallel.
    # N is kept small so the whole layer stays within the 120 s budget even if
    # mirrors are slow. The executor is shut down without waiting so stragglers
    # cannot hold up the worker.
    enrich_limit = min(4, len(inline_items))
    enriched: dict[str, dict] = {}
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    try:
        futures = {
            pool.submit(_fetch_tweet_detail, session, it["user"], it["id"], logger): it
            for it in inline_items[:enrich_limit]
        }
        done, _ = concurrent.futures.wait(
            list(futures), timeout=10, return_when=concurrent.futures.ALL_COMPLETED
        )
        for fut in done:
            it = futures[fut]
            try:
                raw, src = fut.result()
            except Exception as exc:  # noqa: BLE001
                logger.debug("mirror detail failed for %s/%s: %s", it["user"], it["id"], exc)
                continue
            if raw is not None:
                enriched[it["id"]] = _normalize_tweet(it["user"], it["id"], raw, src)
    finally:
        pool.shutdown(wait=False)

    items: list[dict] = []
    for it in inline_items:
        if it["id"] in enriched:
            items.append(enriched[it["id"]])
        else:
            # Use the inline item. Ensure it has a created_at string for the
            # orchestrator, even if it was only a text snippet.
            if it.get("created_at") is None and it.get("created_epoch") is not None:
                it["created_at"] = datetime.fromtimestamp(
                    it["created_epoch"], tz=timezone.utc
                ).isoformat()
            items.append(it)
    return items


# ====================================================================
# Layer 2 - SECONDARY: curl_cffi + x.com/{user} profile
# ====================================================================
def fetch_via_x_profiles(
    session: requests.Session,
    logger,
    accounts: list[str] | None = None,
    per_account_limit: int = 8,
    profile_timeout: int = 8,
) -> list[dict]:
    """Scrape ``x.com/<user>`` via curl_cffi for a curated list of finance
    accounts. Returns normalized tweets (via vxtwitter/fxtwitter).

    The x.com HTML for non-logged-in visitors contains relative
    ``/user/status/id`` links. We harvest those IDs and resolve only the most
    recent ones via the mirror APIs in parallel. Because the public profile page
    often surfaces older/curated tweets, this layer is treated as a secondary
    source; the DDG+jina layer is the primary source for recent content.
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
        # Stop early once we have enough candidates; profile HTML is heavy and
        # the DDG layer already supplies the bulk of recent items.
        if len(all_ids) >= 20:
            break

    if failed_accounts:
        logger.info(
            "X secondary path: %d accounts unreachable (%s)",
            len(failed_accounts), ",".join(failed_accounts[:5]),
        )
    logger.info("X secondary path: harvested %d unique tweet IDs from %d accounts",
                len(all_ids), len(accounts))
    if not all_ids:
        return []

    # Resolve the most recent IDs in parallel. Use the snowflake-derived
    # ordering to prioritize recent tweets. We only try mirror details for
    # the very newest ID because the public profile page tends to surface
    # older/curated tweets; the rest are emitted as snowflake-timestamped
    # inline items so they can still pass the --hours window if recent.
    all_ids.sort(key=lambda pair: int(pair[1]), reverse=True)
    candidates = all_ids[:10]
    items: list[dict] = []
    # Try mirror detail for the single most recent candidate only.
    if candidates:
        user, tid = candidates[0]
        raw, src = _fetch_tweet_detail(session, user, tid, logger)
        if raw is not None:
            items.append(_normalize_tweet(user, tid, raw, src))
    # Emit the rest as inline items with snowflake-derived timestamps.
    for user, tid in candidates[1:]:
        epoch = _snowflake_to_epoch(tid)
        items.append({
            "id": tid,
            "url": f"https://x.com/{user}/status/{tid}",
            "user": user,
            "author_name": user,
            "author_handle": user,
            "text": "",
            "created_at": datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat() if epoch else None,
            "created_epoch": epoch,
            "lang": None,
            "source": None,
            "engagement": {},
            "type": "tweet",
            "source_api": "x_profile_snowflake",
        })
    logger.info("X secondary path: emitted %d tweets", len(items))
    return items


# ====================================================================
# Layer 3 - FALLBACK: jina.ai directly on x.com/search
# ====================================================================
def fetch_via_jina_direct(session, query: str, logger) -> list[dict]:
    """Fallback: ask jina.ai directly for x.com search page."""
    logger.info("X fetch: trying jina direct x.com fallback for query=%r", query)
    target = f"https://x.com/search?q={quote_plus(query)}&f=live"
    md = _jina_fetch(session, target, logger, timeout=15)
    if not md:
        return []
    return _extract_inline_tweets(md, limit=10)


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

    # Layer 1: jina.ai + DDG (PRIMARY - fast, recent, inline text + snowflake epoch)
    for q in queries:
        try:
            items = fetch_via_ddg_jina(session, q, logger, per_query_limit=min(limit_per_query, 8))
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

    # Layer 2: curl_cffi + x.com profiles (SECONDARY - no query dependence)
    try:
        secondary = fetch_via_x_profiles(session, logger, accounts=accounts)
    except Exception as exc:  # noqa: BLE001
        logger.warning("x.com profile path raised: %s", exc)
        secondary = []
    if "x_profiles" not in methods_tried and (_HAS_CURL_CFFI or secondary):
        methods_tried.append("x_profiles")
    for it in secondary:
        tid = it.get("id")
        if not tid or tid in seen_ids:
            continue
        seen_ids.add(tid)
        all_items.append(it)

    # Layer 4: yfinance side-channel (cheap, no de-dupe needed)
    for q in queries[:3]:
        try:
            yf = fetch_yfinance_news(session, q, logger, limit=2)
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
            if it.get("type") in ("tweet", "tweet_inline", "yfinance_news"):
                out.append(it)  # unknown age -> keep; orchestrator can drop
            continue
        if within_hours(dt, hours):
            out.append(it)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("X / Twitter worker (DDG+jina primary + curl_cffi secondary + yfinance side-channel)")
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
        help="Disable the curl_cffi + x.com profile secondary path.",
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
        accounts = []  # empty -> secondary layer returns []

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

    has_real_items = any(it.get("type") not in (None, "empty") for it in items)
    if not items:
        items = [{
            "type": "empty",
            "reason": (
                "no X items returned (DDG+jina search returned 0; "
                "curl_cffi + x.com profile harvest returned 0; "
                "vxtwitter / fxtwitter detail lookups all failed; "
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
    return 0 if has_real_items else 2


if __name__ == "__main__":
    sys.exit(main())
