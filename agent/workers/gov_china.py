#!/usr/bin/env python3
"""
gov_china.py - China official policy news worker.

Sources (RSS-first, homepage fallback):
  - 中国政府网最新政策:  http://www.gov.cn/zhengce/zuixin/zhengcezuixin.htm
  - 央行 (PBOC) 货币政策:  http://www.pbc.gov.cn/zhengwugongkai/4081330/4081344/4081395/4081686/index.html
  - 证监会公告:           http://www.csrc.gov.cn/csrc/c100028/c1001005/content.shtml
  - 商务部:               http://www.mofcom.gov.cn/article/ae/

Strategy:
  1. Try the page directly with feedparser (some sites expose RSS link tags we can discover).
  2. If that yields nothing, fall back to HTML scraping of the homepage with regex/BS-light.
  3. Each item carries: source, title, url, published_at, summary, agency.

Usage:
  python gov_china.py                       # last 24h, all four sources
  python gov_china.py --hours 48
  python gov_china.py --sources pbc,csrc   # filter agencies
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    base_parser,
    http_get,
    make_session,
    parse_dt,
    safe_get,
    setup_logger,
    within_hours,
    write_json,
)

SOURCE = "gov_china"

SOURCES: dict[str, dict[str, str]] = {
    "gov": {
        "name": "中国政府网",
        "homepage": "http://www.gov.cn/zhengce/zuixin/zhengcezuixin.htm",
        "homepage_fallback": "https://www.gov.cn/",
        "rss_candidates": [
            "http://www.gov.cn/zhengce/zhengceku.htm",
        ],
    },
    "pbc": {
        "name": "中国人民银行",
        "homepage": "http://www.pbc.gov.cn/zhengwugongkai/4081330/4081344/4081395/4081686/index.html",
        "homepage_fallback": "http://www.pbc.gov.cn/",
        "rss_candidates": [
            "http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html",
        ],
    },
    "csrc": {
        "name": "证监会",
        "homepage": "http://www.csrc.gov.cn/csrc/c100028/c1001005/content.shtml",
        "homepage_fallback": "http://www.csrc.gov.cn/",
        "rss_candidates": [
            "http://www.csrc.gov.cn/csrc/c100028/common_list.shtml",
        ],
    },
    "mofcom": {
        "name": "商务部",
        "homepage": "http://www.mofcom.gov.cn/article/ae/",
        "homepage_fallback": "http://www.mofcom.gov.cn/",
        "rss_candidates": [],
    },
}

TITLE_LINK_RE = re.compile(
    r'<a[^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<title>[^<]{4,200})</a>',
    re.IGNORECASE,
)


def _fetch_html(session, url: str, logger) -> str | None:
    resp = http_get(
        session,
        url,
        headers={"Referer": url, "Accept": "text/html,application/xhtml+xml"},
        timeout=25,
    )
    if resp is None or resp.status_code != 200:
        logger.warning("HTML fetch %s failed: %s", url, getattr(resp, "status_code", None))
        return None
    try:
        # gov sites are usually GBK / GB18030
        return resp.content.decode("utf-8", errors="replace")
    except Exception:
        return resp.text


def _try_feedparser(session, candidates: list[str], logger) -> list[dict]:
    try:
        import feedparser  # type: ignore
    except ImportError:
        logger.debug("feedparser not available, skipping RSS path")
        return []
    for feed_url in candidates:
        resp = http_get(session, feed_url, timeout=20)
        if resp is None or resp.status_code != 200:
            continue
        try:
            parsed = feedparser.parse(resp.content)
        except Exception as exc:
            logger.debug("feedparser parse %s failed: %s", feed_url, exc)
            continue
        if not parsed.entries:
            continue
        out: list[dict] = []
        for e in parsed.entries:
            out.append(
                {
                    "title": getattr(e, "title", "").strip(),
                    "url": getattr(e, "link", ""),
                    "published_at": getattr(e, "published", None) or getattr(e, "updated", None),
                    "summary": getattr(e, "summary", ""),
                    "source_feed": feed_url,
                }
            )
        if out:
            logger.info("RSS %s returned %d entries", feed_url, len(out))
            return out
    return []


def _scrape_homepage(session, homepage: str, logger) -> list[dict]:
    """Best-effort HTML scraping: pull <a>title</a> pairs with absolute hrefs."""
    html = _fetch_html(session, homepage, logger)
    if not html:
        return []
    out: list[dict] = []
    seen_urls: set[str] = set()
    for m in TITLE_LINK_RE.finditer(html):
        title = (m.group("title") or "").strip()
        href = (m.group("href") or "").strip()
        if not title or not href or len(title) < 4:
            continue
        if href.startswith("javascript:") or href.startswith("#"):
            continue
        absolute = urljoin(homepage, href)
        if absolute in seen_urls:
            continue
        seen_urls.add(absolute)
        out.append(
            {
                "title": title,
                "url": absolute,
                "published_at": None,
                "summary": None,
                "source_feed": homepage,
            }
        )
    logger.info("HTML scrape %s yielded %d candidate links", homepage, len(out))
    return out[:60]  # cap per source


def fetch_one(session, key: str, cfg: dict[str, str], logger) -> list[dict]:
    items = _try_feedparser(session, cfg.get("rss_candidates", []), logger)
    if not items:
        items = _scrape_homepage(session, cfg["homepage"], logger)
    if not items and cfg.get("homepage_fallback"):
        items = _scrape_homepage(session, cfg["homepage_fallback"], logger)
    # Annotate
    for it in items:
        it["agency"] = key
        it["agency_name"] = cfg["name"]
        it["source"] = "gov_china"
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
    parser = base_parser("China official policy news worker (gov / PBOC / CSRC / MOFCOM)")
    parser.add_argument(
        "--sources",
        type=str,
        default=",".join(SOURCES.keys()),
        help=f"Comma-separated agency keys. Available: {','.join(SOURCES.keys())}",
    )
    args = parser.parse_args(argv)

    logger = setup_logger(SOURCE, level="DEBUG" if args.verbose else "INFO")
    session = make_session()
    selected = [s.strip() for s in args.sources.split(",") if s.strip() in SOURCES]

    all_items: list[dict] = []
    for key in selected:
        cfg = SOURCES[key]
        try:
            items = fetch_one(session, key, cfg, logger)
        except Exception as exc:
            logger.warning("source %s raised: %s", key, exc)
            continue
        all_items.extend(items)

    all_items = filter_by_hours(all_items, args.hours)
    if args.limit > 0:
        all_items = all_items[: args.limit]

    if not all_items:
        all_items = [{
            "type": "empty",
            "reason": "no items returned (RSS empty + HTML scrape yielded nothing)",
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