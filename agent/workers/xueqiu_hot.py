#!/usr/bin/env python3
"""xueqiu_hot.py - 雪球 worker.

NOTE (2026-07): All known Xueqiu hot-stock / public-timeline endpoints return
HTTP 400 with ``error_code: 400016`` ("请刷新页面或者重新登录帐号后再试")
when called from a datacenter IP without an authenticated session cookie.

To enable this worker, warm the shared Playwright profile with a manual
Xueqiu login:

    # On the ECS host, in an interactive browser pointed at the profile:
    docker run --rm -it \\
        -v /root/.playwright-profile:/profile:rw \\
        alloyresearch-agent:latest \\
        python -c "
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch_persistent_context('/profile', headless=False)
        page = b.new_page()
        page.goto('https://xueqiu.com/')
        input('login then press enter...')
        b.close()
    "

Once logged in, the worker should be extended to read cookies from the
profile dir. For now it gracefully returns an empty list.

We still attempt a few "public" endpoints; if any return data we capture it.

Usage:
    python xueqiu_hot.py --hours 24 --output /data/xueqiu/hot.json
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

SOURCE = "雪球"
ENDPOINTS = [
    # Trending tickers (no auth required by docs; in practice returns 400016).
    ("https://stock.xueqiu.com/v5/stock/hot_stock/list.json?type=10&size=30",
     "trending"),
    # Public timeline (also 400016 in practice).
    ("https://xueqiu.com/v4/statuses/public_timeline_by_category.json"
     "?category=6&count=20",
     "timeline"),
]
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://xueqiu.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch Xueqiu hot stocks / posts")
    add_common_args(p)
    return p.parse_args()


def _item_from_ticker(raw: dict) -> dict | None:
    name = (raw.get("name") or raw.get("symbol") or "").strip()
    if not name:
        return None
    desc = (raw.get("description") or raw.get("concept") or "").strip()
    sym = raw.get("symbol") or name
    url = f"https://xueqiu.com/snowman/S/{sym}/detail" if sym else "https://xueqiu.com/"
    return {
        "title": f"{name} - {raw.get('rank', '?')} | {desc[:80]}",
        "url": url,
        "published_at": to_iso_utc(None),
        "summary": truncate(desc or f"xueqiu trending {sym}", 500),
        "source": f"{SOURCE}(热股)",
    }


def _item_from_post(raw: dict) -> dict | None:
    title = (raw.get("title") or raw.get("text") or "").strip()
    if not title:
        return None
    user = (raw.get("user") or {}).get("screen_name", "xueqiu")
    sid = raw.get("id")
    url = (f"https://xueqiu.com{raw.get('target', '')}"
           if raw.get("target") else
           f"https://xueqiu.com/{user}/{sid}")
    return {
        "title": truncate(title, 200),
        "url": url,
        "published_at": to_iso_utc(raw.get("created_at")),
        "summary": truncate(raw.get("description") or raw.get("text") or "", 500),
        "source": f"{SOURCE}({user})",
    }


def collect(hours: int, max_pages: int, rate: float, timeout: int,
            max_retries: int, max_items: int) -> list[dict]:
    sess = requests.Session()
    sess.headers.update(HEADERS)
    seen: set[str] = set()
    out: list[dict] = []
    auth_blocked = 0
    for url, kind in ENDPOINTS:
        data = fetch_with_retry(
            lambda u=url: sess.get(u, timeout=timeout),
            max_retry=max_retries, rate=rate,
        )
        if not data:
            LOG.warning("endpoint %s returned no data", kind)
            auth_blocked += 1
            continue
        if kind == "trending":
            items = data.get("data") or data.get("items") or []
            for raw in items:
                rec = _item_from_ticker(raw)
                if rec and rec["url"] not in seen:
                    seen.add(rec["url"])
                    out.append(rec)
            LOG.info("trending: %d items", len(items))
        elif kind == "timeline":
            items = (data.get("statuses") or data.get("items") or [])
            for raw in items:
                rec = _item_from_post(raw)
                if not rec:
                    continue
                key = rec["url"] + rec["title"][:32]
                if key in seen:
                    continue
                seen.add(key)
                out.append(rec)
            LOG.info("timeline: %d items", len(items))
        if len(out) >= max_items:
            break
    if auth_blocked == len(ENDPOINTS) and not out:
        LOG.warning("all Xueqiu endpoints blocked (400016). "
                    "Worker needs an authenticated session cookie. "
                    "See docstring for warm-up instructions.")
    return out[:max_items]


def main() -> int:
    args = parse_args()
    configure_logging(args.verbose)
    try:
        items = collect(args.hours, args.max_pages, args.rate,
                        args.timeout, args.max_retries, args.max_items)
    except Exception as e:  # noqa: BLE001
        LOG.exception("collection failed: %s", e)
        write_output(args.output, [], source=SOURCE)
        return 1
    write_output(args.output, items, source=SOURCE)
    return 0 if items else 2


if __name__ == "__main__":
    sys.exit(main())