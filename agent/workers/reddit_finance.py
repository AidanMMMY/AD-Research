#!/usr/bin/env python3
"""reddit_finance.py - Reddit 财经板块 worker.

Pulls hot posts from several finance-flavored subreddits using Reddit's public
JSON endpoints (no auth needed, just supply a unique User-Agent per Reddit's
API rules). Pagination via the `after` cursor token.

Subreddits:
    wallstreetbets, stocks, investing, StockMarket, options, finance

Usage:
    python reddit_finance.py --hours 24 --output /data/reddit/finance.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    LOG, add_common_args, configure_logging, fetch_with_retry,
    to_iso_utc, truncate, write_output,
)

SOURCE = "Reddit"
SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
    "StockMarket",
    "options",
    "finance",
]
BASE_URL = "https://www.reddit.com"
HEADERS = {
    # Reddit requires a descriptive UA per its API rules.
    "User-Agent": "ad-research-bot/1.0 (research; contact: research@ad-research.local)",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch Reddit finance subreddits")
    add_common_args(p)
    p.add_argument("--sort", default="hot", choices=["hot", "new", "top"],
                   help="post sort order (default: hot)")
    p.add_argument("--top-time", default="day", choices=["hour", "day", "week", "month"],
                   help="time window for 'top' sort (default: day)")
    return p.parse_args()


def _post_to_record(post: dict) -> dict | None:
    if post.get("stickied"):
        return None
    title = (post.get("title") or "").strip()
    if not title:
        return None
    permalink = post.get("permalink") or ""
    return {
        "title": title,
        "url": f"https://www.reddit.com{permalink}" if permalink else post.get("url", ""),
        "published_at": to_iso_utc(post.get("created_utc")),
        "summary": truncate(post.get("selftext") or title, 500),
        "source": f"{SOURCE}/r/{post.get('subreddit', '')}",
    }


def collect(hours: int, max_pages: int, rate: float, timeout: int,
            max_retries: int, max_items: int, sort: str, top_time: str) -> list[dict]:
    sess = requests.Session()
    sess.headers.update(HEADERS)
    seen: set[str] = set()
    out: list[dict] = []
    per_sub_pages = max(1, max_pages // max(1, len(SUBREDDITS)))
    for sub in SUBREDDITS:
        after = None
        for page in range(per_sub_pages):
            url = f"{BASE_URL}/r/{sub}/{sort}.json?limit=50"
            if sort == "top":
                url += f"&t={top_time}"
            if after:
                url += f"&after={after}"
            data = fetch_with_retry(
                lambda u=url: sess.get(u, timeout=timeout),
                max_retry=max_retries, rate=rate,
            )
            if not data:
                LOG.warning("r/%s page %d: no data", sub, page)
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
                if len(out) >= max_items:
                    LOG.info("hit max_items=%d, stopping", max_items)
                    return out[:max_items]
            after = (data.get("data") or {}).get("after")
            if not after:
                LOG.info("r/%s page %d: no more pages", sub, page)
                break
            LOG.info("r/%s page %d: +%d posts, total=%d",
                     sub, page, len(children), len(out))
    return out[:max_items]


def main() -> int:
    args = parse_args()
    configure_logging(args.verbose)
    try:
        items = collect(args.hours, args.max_pages, args.rate,
                        args.timeout, args.max_retries, args.max_items,
                        args.sort, args.top_time)
    except Exception as e:  # noqa: BLE001
        LOG.exception("collection failed: %s", e)
        write_output(args.output, [], source=SOURCE)
        return 1
    write_output(args.output, items, source=SOURCE)
    return 0 if items else 2


if __name__ == "__main__":
    sys.exit(main())