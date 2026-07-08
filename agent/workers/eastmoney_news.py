#!/usr/bin/env python3
"""eastmoney_news.py - 东方财富 worker.

Pulls A-share company announcements from Eastmoney's public API. The legacy
news-feed endpoint (np-listapi ... web_news_col_*) currently returns empty
payloads from datacenter IPs (likely CloudWAF silent-block), so we use the
``np-anotice-stock`` announcements endpoint which is public, paginated, and
returns rich structured data (announcement title, company, time, type).

For each announcement we construct the real detail page URL and then call the
same content API used by the Eastmoney detail page (``np-cnotice-stock``) to
fetch the full body text, including all paginated content.  The resulting text
is stripped of Eastmoney UI button text (展开/转发/收藏 icons etc.) before
being written to the output JSON.

We also probe the news feed as a secondary strategy; if it returns data we
merge it in.

Usage:
    python eastmoney_news.py --hours 24 --output /data/eastmoney_news/today.json
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    LOG, add_common_args, configure_logging, fetch_with_retry,
    to_iso_utc, truncate, write_output,
)

SOURCE = "东方财富"
ANNOUNCEMENT_ENDPOINT = (
    "https://np-anotice-stock.eastmoney.com/api/security/ann"
)
CONTENT_ENDPOINT = "https://np-cnotice-stock.eastmoney.com/api/content/ann"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://data.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
ANNOUNCEMENT_TYPES = [
    # (ann_type, label) - A = A-share, HK = HK-share, US = US-listco
    ("A", "A股公告"),
    ("HK", "港股公告"),
    ("US", "美股中概公告"),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch Eastmoney announcements + news")
    add_common_args(p)
    return p.parse_args()


def _clean_content(text: str) -> str:
    """Strip trailing whitespace, HTML tags, and Eastmoney UI button text."""
    if not text:
        return ""
    # Normalize line endings.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Rich/expanded content sometimes comes with inline HTML tags; strip them.
    if "<" in text and ">" in text:
        text = html.unescape(re.sub(r"<[^>]+>", "", text))
    # Remove the Eastmoney action bar that appears after the article body:
    #   展开  转发  19  45  收藏
    # We only remove it when it is at the very end of the text and requires the
    # expand icon () so that legitimate body text such as "展开合作" is kept.
    text = re.sub(
        r"\n\s*展开\s*\s*(?:\s*转发)?(?:\s*\s*\d+)?"
        r"(?:\s*\s*\d+)?(?:\s*\s*收藏)?\s*$",
        "",
        text,
        flags=re.UNICODE,
    )
    # Remove any leftover private-use-area icons (e.g. , , , , ).
    text = re.sub(r"[--]", "", text)
    # Collapse runs of blank lines.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.rstrip()


def _normalize_announcement(raw: dict, label: str) -> dict | None:
    title = (raw.get("title") or raw.get("title_ch") or "").strip()
    if not title:
        return None
    codes = raw.get("codes") or []
    stock_code = ""
    short_name = ""
    if codes:
        c = codes[0]
        stock_code = c.get("stock_code", "")
        short_name = c.get("short_name", "")
    columns = raw.get("columns") or []
    col_name = columns[0].get("column_name", "") if columns else ""
    art_code = raw.get("art_code", "")
    # Real detail URLs include the stock code: /notices/detail/{stock}/{art_code}.html
    if stock_code and art_code:
        url = f"https://data.eastmoney.com/notices/detail/{stock_code}/{art_code}.html"
    elif art_code:
        url = f"https://data.eastmoney.com/notices/detail/{art_code}.html"
    else:
        url = "https://data.eastmoney.com/notices/"
    return {
        "title": (f"[{short_name}] {title}" if short_name else title).strip(),
        "url": url,
        "published_at": to_iso_utc(
            raw.get("notice_date") or raw.get("display_time")
        ),
        "summary": truncate(
            f"{label} | {col_name} | stock={stock_code}", 500
        ),
        "source": f"{SOURCE}({label})",
        "_art_code": art_code,
    }


def _fetch_content(
    sess: requests.Session,
    art_code: str,
    timeout: int,
    max_retries: int,
    rate: float,
) -> str:
    """Fetch the full announcement body from the Eastmoney content API.

    The API paginates long announcements; we fetch every page and concatenate.
    """
    pieces: list[str] = []
    seen: set[str] = set()
    total_pages = 1
    page = 1
    while page <= total_pages:
        params = {
            "art_code": art_code,
            "client_source": "web",
            "page_index": str(page),
            "cb": "",
        }
        data = fetch_with_retry(
            lambda p=params: sess.get(CONTENT_ENDPOINT, params=p,
                                      timeout=timeout),
            max_retry=max_retries, rate=rate,
        )
        if not data or not data.get("data"):
            LOG.warning("content %s page %d: no data", art_code, page)
            break
        d = data["data"]
        content = (d.get("notice_content") or "").strip()
        if not content or content in seen:
            break
        seen.add(content)
        pieces.append(content)
        # page_size returned by the API is the total number of pages for this
        # language; cap it at 500 to avoid runaway loops while still fetching
        # full annual-report style announcements.
        if page == 1:
            total_pages = d.get("page_size") or 1
            if total_pages < 1:
                total_pages = 1
            total_pages = min(total_pages, 500)
        # Small polite delay between content pages to avoid tripping the
        # Eastmoney server / CDN connection limits.
        if page < total_pages:
            time.sleep(max(rate * 0.2, 0.05))
        page += 1
    return "\n".join(pieces)


def _enrich_content(
    item: dict,
    sess: requests.Session,
    timeout: int,
    max_retries: int,
    rate: float,
) -> None:
    """Fetch the full body text for a single announcement item."""
    art_code = item.pop("_art_code", "")
    if not art_code:
        item["content"] = ""
        return
    try:
        content = _fetch_content(sess, art_code, timeout, max_retries, rate)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("content fetch failed for %s: %s", art_code, exc)
        content = ""
    item["content"] = _clean_content(content)


def _fetch_announcements(sess: requests.Session, ann_type: str, label: str,
                         hours: int, page_size: int, max_pages: int,
                         timeout: int, max_retries: int, rate: float,
                         seen: set[str], out: list[dict], max_items: int) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    for page in range(1, max_pages + 1):
        params = {
            "cb": "",
            "page_size": str(page_size),
            "page_index": str(page),
            "ann_type": ann_type,
            "client_source": "web",
            "stock_list": "",
            "f_node": "0",
            "s_node": "0",
        }
        data = fetch_with_retry(
            lambda p=params: sess.get(ANNOUNCEMENT_ENDPOINT, params=p,
                                      timeout=timeout),
            max_retry=max_retries, rate=rate,
        )
        if not data:
            LOG.warning("ann %s page %d: no data", ann_type, page)
            break
        lst = (((data.get("data") or {}).get("list")) or [])
        if not lst:
            LOG.info("ann %s page %d: empty, stopping", ann_type, page)
            break
        oldest = None
        for raw in lst:
            rec = _normalize_announcement(raw, label)
            if not rec:
                continue
            try:
                rec_dt = datetime.fromisoformat(
                    rec["published_at"].replace("Z", "+00:00")
                )
                if rec_dt.tzinfo is None:
                    rec_dt = rec_dt.replace(tzinfo=timezone.utc)
                if oldest is None or rec_dt < oldest:
                    oldest = rec_dt
                if rec_dt < cutoff:
                    LOG.info("ann %s page %d: cutoff reached",
                             ann_type, page)
                    return
            except (ValueError, AttributeError):
                pass
            key = rec["url"] + rec["title"][:64]
            if key in seen:
                continue
            seen.add(key)
            out.append(rec)
            if len(out) >= max_items:
                LOG.info("hit max_items=%d, stopping", max_items)
                return
        LOG.info("ann %s page %d: +%d total=%d",
                 ann_type, page, len(lst), len(out))


def collect(hours: int, max_pages: int, rate: float, timeout: int,
            max_retries: int, max_items: int, page_size: int = 30) -> list[dict]:
    sess = requests.Session()
    sess.headers.update(HEADERS)
    seen: set[str] = set()
    out: list[dict] = []
    for ann_type, label in ANNOUNCEMENT_TYPES:
        _fetch_announcements(
            sess, ann_type, label, hours, page_size,
            max_pages, timeout, max_retries, rate, seen, out, max_items,
        )
        if len(out) >= max_items:
            break
    # Fetch the full announcement body for every collected item.  We use a
    # dedicated session for the content API and run sequentially to avoid
    # triggering Eastmoney's connection/rate limits.
    if out:
        content_sess = requests.Session()
        content_sess.headers.update(HEADERS)
        for item in out:
            _enrich_content(item, content_sess, timeout, max_retries, rate)
    return out


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
