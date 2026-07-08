#!/usr/bin/env python3
"""
fed_intl.py - Fed / ECB / BIS / IMF official news worker.

RSS endpoints (all public, feedparser-friendly):
  - Fed press releases:  https://www.federalreserve.gov/feeds/press_all.xml
  - Fed speeches:        https://www.federalreserve.gov/feeds/speeches.xml
  - ECB press:           https://www.ecb.europa.eu/rss/press.html
  - BIS central bank:    https://www.bis.org/doclist/cbsl_publs.rss
  - IMF press:           https://www.imf.org/external/np/sec/pr/Channel.aspx?Channel=RSS

Usage:
  python fed_intl.py                                # all 4, last 24h
  python fed_intl.py --sources fed,bis --hours 48
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

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

SOURCE = "fed_intl"

FEEDS: dict[str, dict[str, Any]] = {
    "fed": {
        "name": "Federal Reserve",
        "urls": [
            "https://www.federalreserve.gov/feeds/press_all.xml",
            "https://www.federalreserve.gov/feeds/speeches.xml",
            "https://www.federalreserve.gov/feeds/calendar.xml",
        ],
    },
    "ecb": {
        "name": "European Central Bank",
        "urls": [
            "https://www.ecb.europa.eu/rss/press.html",
            "https://www.ecb.europa.eu/rss/speeches.html",
            "https://www.ecb.europa.eu/rss/decisions.html",
        ],
    },
    "bis": {
        "name": "Bank for International Settlements",
        "urls": [
            "https://www.bis.org/doclist/all_pressrels.rss",
            "https://www.bis.org/doclist/cbspeeches.rss?paging_length=15",
            "https://www.bis.org/doclist/rss_all_categories.rss",
        ],
    },
    "imf": {
        "name": "International Monetary Fund",
        "urls": [
            # IMF aggressively blocks datacenter IPs (HTTP 403 from ECS / cloud).
            # Keep these as best-effort; the homepage scrape fallback covers the gap.
            "https://www.imf.org/external/np/sec/pr/Channel.aspx?Channel=RSS",
            "https://www.imf.org/external/np/sec/mpr/Channel.aspx?Channel=RSS",
        ],
        "homepage": "https://www.imf.org/en/News",
    },
}


def _parse_feed(session, url: str, logger) -> list[dict]:
    try:
        import feedparser  # type: ignore
    except ImportError:
        logger.error("feedparser is required for fed_intl.py. pip install feedparser")
        return []
    resp = http_get(session, url, timeout=25)
    if resp is None or resp.status_code != 200:
        logger.warning("RSS fetch %s failed: %s", url, getattr(resp, "status_code", None))
        return []
    try:
        parsed = feedparser.parse(resp.content)
    except Exception as exc:
        logger.warning("feedparser %s exception: %s", url, exc)
        return []
    if not parsed.entries:
        logger.info("RSS %s empty", url)
        return []
    out: list[dict] = []
    for e in parsed.entries:
        out.append(
            {
                "title": getattr(e, "title", "").strip(),
                "url": getattr(e, "link", ""),
                "published_at": getattr(e, "published", None) or getattr(e, "updated", None),
                "summary": getattr(e, "summary", "")[:600] if getattr(e, "summary", None) else None,
                "author": getattr(e, "author", None),
                "tags": [t.get("term") for t in getattr(e, "tags", []) or []],
                "feed_url": url,
            }
        )
    logger.info("RSS %s -> %d entries", url, len(out))
    return out


def fetch_source(session, key: str, cfg: dict[str, Any], logger) -> list[dict]:
    items: list[dict] = []
    for u in cfg["urls"]:
        items.extend(_parse_feed(session, u, logger))
    # Homepage scrape fallback (helps when RSS is blocked, e.g. IMF)
    if not items and cfg.get("homepage"):
        try:
            from common import http_get as _http_get  # local alias for readability
            import re as _re
            from urllib.parse import urljoin as _urljoin
            resp = _http_get(session, cfg["homepage"], timeout=20)
            if resp is not None and resp.status_code == 200:
                html = resp.text
                link_re = _re.compile(
                    r'<a[^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<title>[^<]{6,200})</a>',
                    _re.IGNORECASE,
                )
                for m in link_re.finditer(html):
                    title = (m.group("title") or "").strip()
                    href = (m.group("href") or "").strip()
                    if not title or not href or href.startswith(("javascript:", "#")):
                        continue
                    items.append(
                        {
                            "title": title,
                            "url": _urljoin(cfg["homepage"], href),
                            "published_at": None,
                            "summary": None,
                            "feed_url": cfg["homepage"],
                        }
                    )
                logger.info("homepage scrape %s -> %d items", cfg["homepage"], len(items))
        except Exception as exc:
            logger.warning("homepage scrape fallback for %s failed: %s", key, exc)
    # Annotate
    for it in items:
        it["agency"] = key
        it["agency_name"] = cfg["name"]
        it["source"] = "fed_intl"
    return items


def filter_by_hours(items: list[dict], hours: int) -> list[dict]:
    if hours <= 0:
        return items
    out = []
    for it in items:
        dt = parse_dt(it.get("published_at"))
        if within_hours(dt, hours):
            out.append(it)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = base_parser("Fed / ECB / BIS / IMF official news worker")
    parser.add_argument(
        "--sources",
        type=str,
        default=",".join(FEEDS.keys()),
        help=f"Comma-separated agency keys. Available: {','.join(FEEDS.keys())}",
    )
    args = parser.parse_args(argv)

    logger = setup_logger(SOURCE, level="DEBUG" if args.verbose else "INFO")
    session = make_session()
    selected = [s.strip() for s in args.sources.split(",") if s.strip() in FEEDS]

    all_items: list[dict] = []
    for key in selected:
        cfg = FEEDS[key]
        try:
            all_items.extend(fetch_source(session, key, cfg, logger))
        except Exception as exc:
            logger.warning("source %s raised: %s", key, exc)

    # dedupe by URL
    seen = set()
    deduped: list[dict] = []
    for it in all_items:
        u = it.get("url")
        if u and u in seen:
            continue
        if u:
            seen.add(u)
        deduped.append(it)
    all_items = deduped

    all_items = filter_by_hours(all_items, args.hours)
    if args.limit > 0:
        all_items = all_items[: args.limit]

    if not all_items:
        all_items = [{
            "type": "empty",
            "reason": "no entries from any RSS feed (network blocked or feeds temporarily empty)",
            "sources_attempted": selected,
        }]

    write_json(
        all_items,
        source=SOURCE,
        out_path=args.output,
        data_root=args.data_root,
        limit=args.limit,
        logger=logger,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())