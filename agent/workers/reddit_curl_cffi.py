#!/usr/bin/env python3
"""reddit_curl_cffi.py - Reddit finance worker with curl_cffi TLS impersonation.

Uses curl_cffi to impersonate real browser JA3/H2 fingerprints so the HTTP
request looks like Chrome / Firefox / Safari on the wire. This is the
second-line mitigation after the ECS IP was 403-blocked by Reddit WAF.

> Verified 2026-07-07 against ECS 47.239.13.111: every impersonate profile
> across www/old/i.reddit.com returns the same Reddit WAF 403 page. The block
> is purely IP-reputation based, so this worker ships with a --proxy hook
> for when a residential proxy is provisioned.

Usage:
    python reddit_curl_cffi.py --hours 24 --output /data/reddit/finance.json
    python reddit_curl_cffi.py --subreddit wallstreetbets --hours 24 \\
        --impersonate chrome124 --proxy http://user:pass@host:port \\
        --output /data/reddit/wsb.json
    python reddit_curl_cffi.py --dry-run    # probe every profile
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

try:
    from curl_cffi import requests as cffi_requests
    from curl_cffi.requests import BrowserType
except ImportError:
    print("ERROR: curl_cffi not installed. "
          "Run: pip3 install --break-system-packages curl_cffi", file=sys.stderr)
    raise

# --- Self-contained helpers (intentionally do NOT import common.py, which
#     has diverged across worker revisions and no longer exports LOG/truncate/
#     to_iso_utc/etc. used here).
import json
from datetime import datetime, timezone

LOG = logging.getLogger("ad-research.reddit_curl_cffi")

UA_CHROME  = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 "
              "Safari/537.36")
UA_FIREFOX = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) "
              "Gecko/20100101 Firefox/135.0")
UA_SAFARI  = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/605.1.15 (KHTML, like Gecko) "
              "Version/17.4 Safari/605.1.15")


def _iso_utc(ts):
    if ts is None:
        return datetime.now(tz=timezone.utc).isoformat()
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return str(ts)


def _truncate(text, n=500):
    if not text:
        return ""
    s = str(text).strip()
    return s if len(s) <= n else s[:n].rstrip() + "..."


def _filter_by_hours(items, hours):
    if hours <= 0:
        return list(items)
    cutoff = datetime.now(tz=timezone.utc).timestamp() - hours * 3600
    out = []
    for it in items:
        ts = it.get("published_at", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt.timestamp() < cutoff:
                continue
        except (ValueError, AttributeError):
            pass
        out.append(it)
    return out


def _write_output(path, items, *, source):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    for it in items:
        it.setdefault("source", source)
    tmp = Path(path).with_suffix(Path(path).suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
    LOG.info("wrote %d items to %s (%d bytes)",
             len(items), path, Path(path).stat().st_size)


def _configure_logging(verbose=False):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


SOURCE = "Reddit"

# finance-flavored subreddits
DEFAULT_SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
    "StockMarket",
    "options",
    "finance",
]

# All curl_cffi 0.15 impersonate profiles (cross-checked at runtime)
IMPERSONATE_PROFILES = [
    "chrome99", "chrome100", "chrome101", "chrome104", "chrome107",
    "chrome110", "chrome116", "chrome119", "chrome120", "chrome123",
    "chrome124", "chrome131", "chrome133a", "chrome136", "chrome142",
    "chrome145", "chrome146",
    "chrome99_android", "chrome131_android",
    "edge99", "edge101",
    "firefox133", "firefox135", "firefox147",
    "safari15_3", "safari15_5", "safari17_0", "safari17_2_ios",
    "safari18_0", "safari18_0_ios", "safari184", "safari184_ios",
    "safari260", "safari2601",
]

# (UA constants live in the header block above)


def _ua_for(profile: str) -> str:
    if profile.startswith("firefox"):
        return UA_FIREFOX
    if profile.startswith("safari"):
        return UA_SAFARI
    return UA_CHROME  # chrome / edge default


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Fetch Reddit finance subreddits via curl_cffi")
    p.add_argument("--hours", type=int, default=24,
                   help="time window in hours (default: 24)")
    p.add_argument("--output", type=Path, default=None,
                   help="output JSON file path")
    p.add_argument("--rate", type=float, default=1.0,
                   help="seconds between HTTP requests (default: 1.0)")
    p.add_argument("--timeout", type=int, default=20,
                   help="HTTP timeout seconds (default: 20)")
    p.add_argument("--max-retries", type=int, default=3,
                   help="max retries per HTTP request (default: 3)")
    p.add_argument("--max-pages", type=int, default=4,
                   help="max pagination rounds (default: 4)")
    p.add_argument("--max-items", type=int, default=200,
                   help="max items to keep in output (default: 200)")
    p.add_argument("--subreddit", "-s",
                   help="single subreddit (without r/). Overrides default list.")
    p.add_argument("--all-subs", action="store_true",
                   help="ignore --subreddit and use the full default list")
    p.add_argument("--impersonate", "-i", default="chrome124",
                   choices=IMPERSONATE_PROFILES,
                   help="TLS-fingerprint profile (default: chrome124)")
    p.add_argument("--proxy",
                   help="HTTP/HTTPS proxy URL, e.g. http://user:pass@host:port")
    p.add_argument("--domain", default="www",
                   choices=["www", "old", "i"],
                   help="Reddit subdomain to hit (default: www)")
    p.add_argument("--sort", default="new",
                   choices=["hot", "new", "top"],
                   help="post sort order (default: new)")
    p.add_argument("--top-time", default="day",
                   choices=["hour", "day", "week", "month"],
                   help="time window for top sort (default: day)")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="verbose logging")
    p.add_argument("--dry-run", action="store_true",
                   help="probe each impersonate profile once and exit")
    return p.parse_args()


def _post_to_record(post: dict) -> dict | None:
    if post.get("stickied"):
        return None
    title = (post.get("title") or "").strip()
    if not title:
        return None
    permalink = post.get("permalink") or ""
    return {
        "title": _truncate(title, 280),
        "url": (f"https://www.reddit.com{permalink}" if permalink
                else post.get("url", "")),
        "published_at": _iso_utc(post.get("created_utc")),
        "summary": _truncate(post.get("selftext") or title, 500),
        "source": SOURCE + "/r/" + (post.get("subreddit") or ""),
    }


def build_session(args: argparse.Namespace):
    """Single session carrying headers + impersonation + optional proxy."""
    sess = cffi_requests.Session()
    sess.headers.update({
        "User-Agent": _ua_for(args.impersonate),
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    })
    if args.proxy:
        sess.proxies = {"http": args.proxy, "https": args.proxy}
        LOG.info("using proxy: %s", args.proxy)
    return sess


def _url(args: argparse.Namespace, sub: str, after: str | None) -> str:
    base = f"https://{args.domain}.reddit.com"
    url = f"{base}/r/{sub}/{args.sort}.json?limit=100&raw_json=1"
    if args.sort == "top":
        url += f"&t={args.top_time}"
    if after:
        url += f"&after={after}"
    return url


def _do_get(sess, url: str, args: argparse.Namespace):
    try:
        return sess.get(url, impersonate=args.impersonate, timeout=args.timeout)
    except Exception as e:  # noqa: BLE001
        LOG.warning("impersonate=%s failed on %s (%s); retrying bare",
                    args.impersonate, url, type(e).__name__)
        return sess.get(url, timeout=args.timeout)


def collect(args: argparse.Namespace) -> list[dict]:
    subs = (DEFAULT_SUBREDDITS if (args.all_subs or not args.subreddit)
            else [args.subreddit])
    sess = build_session(args)
    seen: set[str] = set()
    out: list[dict] = []
    per_sub_pages = max(1, args.max_pages // max(1, len(subs)))
    for sub in subs:
        after = None
        for page in range(per_sub_pages):
            url = _url(args, sub, after)
            r = _do_get(sess, url, args)
            if r.status_code == 403:
                LOG.error("r/%s page %d: 403 from %s (ECS IP is on "
                          "Reddit WAF denylist). Configure --proxy.",
                          sub, page, args.domain)
                return out  # bail fast — whole host is blocked
            if r.status_code == 429:
                LOG.warning("r/%s page %d: 429 rate-limited; backing off 5s",
                            sub, page)
                time.sleep(5)
                continue
            if not (200 <= r.status_code < 300):
                LOG.warning("r/%s page %d: HTTP %d", sub, page, r.status_code)
                break
            try:
                data = r.json()
            except ValueError:
                LOG.warning("r/%s page %d: non-JSON body", sub, page)
                break
            children = (data.get("data") or {}).get("children") or []
            if not children:
                LOG.info("r/%s page %d: empty, stopping sub", sub, page)
                break
            for ch in children:
                post = ch.get("data") or {}
                rec = _post_to_record(post)
                if not rec:
                    continue
                key = rec["url"]
                if key in seen:
                    continue
                seen.add(key)
                out.append(rec)
                if len(out) >= args.max_items:
                    LOG.info("hit max_items=%d, stopping", args.max_items)
                    return out[: args.max_items]
            after = (data.get("data") or {}).get("after")
            if not after:
                LOG.info("r/%s page %d: no more pages", sub, page)
                break
            LOG.info("r/%s page %d: +%d posts, total=%d",
                     sub, page, len(children), len(out))
            if args.rate > 0:
                time.sleep(args.rate)
    return out[: args.max_items]


def dry_run(args: argparse.Namespace) -> None:
    """One HTTP call per profile, log HTTP code + body length, then exit."""
    url = (f"https://{args.domain}.reddit.com/r/wallstreetbets/"
           f"{args.sort}.json?limit=5")
    LOG.info("dry-run: probing %s across %d profiles",
             url, len(IMPERSONATE_PROFILES))
    sess = build_session(args)
    print(f"{chr(39)}profile{chr(39):22s} status  bytes    body[:80]")
    print("-" * 90)
    for prof in IMPERSONATE_PROFILES:
        try:
            sess.headers["User-Agent"] = _ua_for(prof)
            args.impersonate = prof
            r = _do_get(sess, url, args)
            snippet = (r.text[:80].replace(chr(10), " ").replace(chr(13), " "))
            print(f"{prof:22s} {r.status_code:>6d} {len(r.text):>6d}    {snippet}")
        except Exception as e:
            print(f"{prof:22s}   EXC    ------  {type(e).__name__}: {e}")
        time.sleep(0.4)


def main() -> int:
    args = parse_args()
    _configure_logging(args.verbose)
    if args.dry_run:
        dry_run(args)
        return 0
    try:
        items = collect(args)
    except Exception as e:  # noqa: BLE001
        LOG.exception("collection failed: %s", e)
        _write_output(args.output, [], source=SOURCE)
        return 1
    items = _filter_by_hours(items, args.hours)
    LOG.info("after hours=%d filter: %d items", args.hours, len(items))
    _write_output(args.output, items, source=SOURCE)
    return 0 if items else 2


if __name__ == "__main__":
    sys.exit(main())
