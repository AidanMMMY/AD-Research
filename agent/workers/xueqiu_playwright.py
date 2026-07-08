#!/usr/bin/env python3
"""Xueqiu hot worker using Playwright persistent context (Linux-compatible).

Reads the persistent profile at /profile (mounted by run_worker.sh), navigates
to multiple Xueqiu pages (home / coin-rank / today / discovery), parses the
rendered HTML/DOM with page.evaluate(), and writes standardized JSON to
--output. Self-contained; no common.py dependency.

Key data sources scraped (each is a separate pass):
- https://xueqiu.com/                       - 热门讨论首页
- https://xueqiu.com/h5/coin/coin-rank      - 热股（移动端排行）
- https://xueqiu.com/today/people           - 关注的人动态
- https://xueqiu.com/discovery/tweet-rank   - 热门动态
- https://xueqiu.com/discovery/pop-rank     - 热门关注

Anti-bot hardening:
- removes navigator.webdriver flag
- random per-action sleep (0.6-1.8s)
- natural viewport (1440x900) plus occasional resize
- realistic browser headers + Accept-Language zh-CN
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

PROFILE_DIR = "/profile"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
SOURCE = "xueqiu"

# ---------------------------------------------------------------------------
# Xueqiu URL configuration
# ---------------------------------------------------------------------------

# Each entry: (url, wait_ms, page_kind, max_items, extra_scrolls)
URL_TARGETS: list[tuple[str, int, str, int, int]] = [
    ("https://xueqiu.com/",                     8000, "home",     40, 4),
    ("https://xueqiu.com/h5/coin/coin-rank",    8000, "coin",     50, 3),
    ("https://xueqiu.com/today/people",         8000, "timeline", 40, 4),
    ("https://xueqiu.com/discovery/tweet-rank", 8000, "discover", 40, 4),
    ("https://xueqiu.com/discovery/pop-rank",   8000, "discover", 30, 2),
]

# Symbol extraction regex (anchored on /s/ + valid exchange prefix or US/HK raw):
#   /s/SH600519 -> 600519.SH
#   /s/SZ000001 -> 000001.SZ
#   /s/BJ830xxx -> 830xxx.BJ
#   /s/00700    -> 00700.HK  (HK is 5-digit zero-padded; raw URL may be un-padded)
#   /s/TSLA     -> TSLA.US
#   /S/SH600519 -> same (legacy, case-insensitive)
# We require the prefix (if any) to be a known exchange (SH/SZ/BJ/HK), otherwise
# we treat the whole body as a US ticker.
_STOCK_HREF_RE = re.compile(
    r"/s/(?:(SH|SZ|BJ|HK)([0-9]{4,6})|([A-Za-z]{1,5})|([0-9]{4,6}))/?",
    re.IGNORECASE,
)
_CASHTAG_RE = re.compile(r"\$([A-Z]{2}\d{4,6}|[A-Z]{1,5})(?:\.[A-Z]{1,3})?\$")
_CN_CODE_RE = re.compile(r"\b(\d{6})\b")  # 6-digit A-share candidate

logger = logging.getLogger("xueqiu-playwright")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _human_sleep(min_s: float = 0.6, max_s: float = 1.8) -> None:
    """Sleep a randomized amount to mimic human pacing."""
    time.sleep(random.uniform(min_s, max_s))


def _stock_symbols_from_url(href: str) -> list[str]:
    """Extract internal-style stock codes from an Xueqiu URL like /s/SH600519."""
    if not href:
        return []
    out: list[str] = []
    for m in _STOCK_HREF_RE.finditer(href):
        exchange, code, us_ticker, hk_raw = m.group(1), m.group(2), m.group(3), m.group(4)
        if exchange and code:
            ex = exchange.upper()
            num = code.lstrip("0") or "0"
            if ex in ("SH", "SZ", "BJ"):
                padded = num.zfill(6)[:6]
                out.append(f"{padded}.{ex}")
            elif ex == "HK":
                out.append(f"{int(num):05d}.HK")
        elif us_ticker:
            # Pure letter ticker is treated as US; but "S"/"SH"/"SZ" alone
            # would have been matched by the alt branch only if the full body
            # is alpha — those are noise, so require length >= 2.
            if len(us_ticker) >= 2:
                out.append(f"{us_ticker.upper()}.US")
        elif hk_raw:
            out.append(f"{int(hk_raw):05d}.HK")
    return list(dict.fromkeys(out))


def _stock_symbols_from_text(text: str) -> list[str]:
    """Extract stock codes mentioned as $SH600519$ cashtags or bare 6-digit codes."""
    out: list[str] = []
    if not text:
        return out
    for m in _CASHTAG_RE.finditer(text):
        body = m.group(1)
        if body.startswith("SH") and body[2:].isdigit():
            out.append(f"{body[2:]}.SH")
        elif body.startswith("SZ") and body[2:].isdigit():
            out.append(f"{body[2:]}.SZ")
        elif body.startswith("BJ") and body[2:].isdigit():
            out.append(f"{body[2:]}.BJ")
        elif body.startswith("HK") and body[2:].isdigit():
            out.append(f"{int(body[2:]):05d}.HK")
        elif body.isalpha():
            out.append(f"{body}.US")
    return list(dict.fromkeys(out))


def _parse_int(text: str) -> int | None:
    """Parse '1.2万', '12,345', '3500' etc into int. Returns None on failure."""
    if text is None:
        return None
    s = str(text).strip().replace(",", "").replace(" ", "")
    if not s:
        return None
    m = re.match(r"^([\d.]+)([万亿]?)$", s)
    if not m:
        digits = re.findall(r"\d+", s)
        if not digits:
            return None
        try:
            return int(digits[0])
        except ValueError:
            return None
    num, unit = m.group(1), m.group(2)
    try:
        base = float(num)
    except ValueError:
        return None
    if unit == "万":
        base *= 1e4
    elif unit == "亿":
        base *= 1e8
    return int(base)


# ---------------------------------------------------------------------------
# Anti-bot: navigator override + headers
# ---------------------------------------------------------------------------


def _anti_bot_init_script() -> str:
    """JS that runs before page scripts; hides webdriver traces."""
    return """
    // Overwrite webdriver flag before any page script runs
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    // Patch plugins / languages to look human
    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    // Hide headless clues
    window.chrome = window.chrome || { runtime: {} };
    """


# ---------------------------------------------------------------------------
# DOM extraction snippets (run inside page.evaluate)
# ---------------------------------------------------------------------------

# Pulls a structured list of post/status cards from the current page.
# Returns up to ``limit`` items with: title, body, author, href, time, counts.
EVALUATE_TIMELINE_JS = r"""
(limit) => {
    const out = [];
    const seen = new Set();

    // Strategy: walk all anchor-looking wrappers and lift text + counts.
    // Xueqiu home uses different containers over time; we sample a wide net.

    const cardSelectors = [
        'article',
        '.timeline__item',
        '.status-item',
        '[class*="status" i]',
        '[class*="Status"]',
        '[class*="timeline" i]',
        '[class*="Timeline"]',
        '[class*="tweet" i]',
        '[class*="Tweet"]',
        '.home-tweet-list .home-tweet-item',
        'div[class*="item"]:has(a[href*="/"])',
    ];

    const isCard = (el) => {
        if (!el || el.dataset && el.dataset._xq_seen) return false;
        const text = (el.innerText || '').trim();
        return text.length >= 8 && text.length <= 4000;
    };

    const collect = (root) => {
        // Try a direct article sweep first
        const candidates = [];
        try {
            candidates.push(...root.querySelectorAll('article'));
        } catch (_) {}
        try {
            candidates.push(...root.querySelectorAll('a[href*="/"]'));
        } catch (_) {}

        for (const el of candidates) {
            if (out.length >= limit) break;
            if (!isCard(el)) continue;
            const card = (el.tagName && el.tagName.toLowerCase() === 'a')
                ? el.closest('article, [class*="status" i], [class*="tweet" i], [class*="timeline" i]') || el
                : el;

            const text = (card.innerText || '').trim();
            if (!text || text.length < 8) continue;

            // Anchor: prefer status / quote links; fall back to first link inside.
            let link = card.querySelector('a[href*="/status/"], a[href*="/q/"]');
            if (!link) {
                // Try direct anchors referencing a stock or user profile
                link = card.querySelector('a[href*="/s/"], a[href*="/u/"]');
            }
            if (!link) {
                link = card.querySelector('a[href]');
            }
            const href = link ? (link.href || '') : '';
            if (!href || href.includes('javascript:')) continue;

            // Skip if we already emitted a card with this href.
            const dedupeKey = href + '|' + text.slice(0, 50);
            if (seen.has(dedupeKey)) continue;
            seen.add(dedupeKey);

            // Author: look for user link inside card
            let author = '';
            const userLink = card.querySelector('a[href*="/u/"]');
            if (userLink) {
                author = (userLink.innerText || '').trim().split('\n')[0].slice(0, 60);
            }

            // Time: any element with 'data-time', or text matching 'XX分钟前' / 'HH:MM'
            let timeText = '';
            const timeEl = card.querySelector('[class*="time" i], [class*="date" i]');
            if (timeEl) timeText = (timeEl.innerText || '').trim();
            if (!timeText) {
                const m = text.match(/(\d{1,2}\s*分钟前|\d{1,2}\s*小时前|\d{1,2}\s*秒前|刚刚|\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}|\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})/);
                if (m) timeText = m[1];
            }

            // Counts: dig out 'xxx 评论' / 'xxx 转发' / 'xxx 赞' / 'xxx 阅读' tokens
            const counts = { likes: 0, comments: 0, reposts: 0, views: 0 };
            const countRegex = /(\d[\d,.]*)\s*(万|亿)?\s*(评论|回复|转发|赞|喜欢|阅读|查看)/g;
            let cm;
            while ((cm = countRegex.exec(text)) !== null) {
                let n = parseFloat(cm[1]);
                const unit = cm[2];
                if (unit === '万') n *= 10000;
                else if (unit === '亿') n *= 100000000;
                const v = Math.round(n);
                const kind = cm[3];
                if (kind === '评论' || kind === '回复') counts.comments = v;
                else if (kind === '转发') counts.reposts = v;
                else if (kind === '赞' || kind === '喜欢') counts.likes = v;
                else if (kind === '阅读' || kind === '查看') counts.views = v;
            }

            // First non-empty line as title; full text as body
            const lines = text.split(/\n+/).map(s => s.trim()).filter(Boolean);
            const title = lines[0] ? lines[0].slice(0, 200) : '';
            const body = text.slice(0, 4000);

            out.push({
                title,
                body,
                author,
                href,
                time_text: timeText,
                counts,
            });
        }
    };

    collect(document);
    return out;
}
"""

# Specialized evaluator for the mobile coin-rank page (rich with stock codes)
EVALUATE_COIN_RANK_JS = r"""
(limit) => {
    const out = [];
    const seen = new Set();

    // The mobile coin-rank page renders each stock inside an anchor
    // containing both the symbol and the company name. We pick the
    // broadest set of stock anchors and lift name/symbol/quote.
    const anchors = Array.from(document.querySelectorAll('a[href*="/s/"], a[href*="/snowman/"]'));
    for (const a of anchors) {
        if (out.length >= limit) break;
        const text = (a.innerText || '').trim();
        if (!text) continue;
        // Pull the first 6-digit code (or alphanumeric ticker) and the Chinese name
        const codeMatch = text.match(/([A-Z]{2}\d{6}|\d{6}|[A-Z]{1,5})/);
        const nameMatch = text.match(/[一-龥A-Za-z·\s]{2,}/);
        const href = a.href || '';
        const key = href + '|' + (codeMatch ? codeMatch[1] : text.slice(0, 30));
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({
            title: (nameMatch ? nameMatch[0].trim() : (codeMatch ? codeMatch[1] : text)).slice(0, 80),
            body: text.slice(0, 800),
            author: '',
            href,
            time_text: '',
            counts: { likes: 0, comments: 0, reposts: 0, views: 0 },
        });
    }
    return out;
}
"""

# Specialized evaluator for the discovery rank pages (lists of user / post cards)
EVALUATE_DISCOVERY_JS = r"""
(limit) => {
    const out = [];
    const seen = new Set();

    // Each row is roughly: a small avatar / username + headline + a metric (粉丝 / 讨论 / 热度)
    const rows = Array.from(document.querySelectorAll(
        '[class*="rank" i], [class*="Rank"], [class*="list" i], [class*="List"] > div, li'
    ));
    for (const row of rows) {
        if (out.length >= limit) break;
        const text = (row.innerText || '').trim();
        if (!text || text.length < 4 || text.length > 1500) continue;
        const link = row.querySelector('a[href]');
        const href = link ? (link.href || '') : '';
        if (!href || href.includes('javascript:')) continue;
        const key = href + '|' + text.slice(0, 60);
        if (seen.has(key)) continue;
        seen.add(key);

        let author = '';
        const userLink = row.querySelector('a[href*="/u/"]');
        if (userLink) author = (userLink.innerText || '').trim().split('\n')[0].slice(0, 60);

        const counts = { likes: 0, comments: 0, reposts: 0, views: 0 };
        const fanMatch = text.match(/(\d[\d,.]*)\s*(万|亿)?\s*(粉丝|关注者)/);
        if (fanMatch) {
            let n = parseFloat(fanMatch[1]);
            if (fanMatch[2] === '万') n *= 10000;
            else if (fanMatch[2] === '亿') n *= 1e8;
            counts.followers = Math.round(n);
        }
        const discussMatch = text.match(/(\d[\d,.]*)\s*(万|亿)?\s*(讨论|热议)/);
        if (discussMatch) {
            let n = parseFloat(discussMatch[1]);
            if (discussMatch[2] === '万') n *= 10000;
            else if (discussMatch[2] === '亿') n *= 1e8;
            counts.discussions = Math.round(n);
        }

        const lines = text.split(/\n+/).map(s => s.trim()).filter(Boolean);
        const title = lines[0] ? lines[0].slice(0, 120) : '';
        out.push({
            title,
            body: text.slice(0, 1500),
            author,
            href,
            time_text: '',
            counts,
        });
    }
    return out;
}
"""


# ---------------------------------------------------------------------------
# Page actions
# ---------------------------------------------------------------------------


def _scroll_for_more(page, logger, scrolls: int = 3, pause_s: float = 1.2) -> None:
    """Scroll the page to trigger lazy-loaded content."""
    try:
        for i in range(max(0, scrolls)):
            page.mouse.wheel(0, random.randint(700, 1200))
            page.wait_for_timeout(int(pause_s * 1000))
            # Try evaluate-based scroll too (some layouts only react to JS scroll)
            page.evaluate(f"window.scrollBy({{ top: {random.randint(700, 1200)}, behavior: 'instant' }});")
            page.wait_for_timeout(int(pause_s * 1000))
            logger.debug(f"scrolled {i + 1}/{scrolls}")
    except Exception as exc:
        logger.debug(f"scroll_for_more: {exc}")


def _dismiss_overlays(page, logger) -> None:
    """Try to close login walls / cookie banners / popups so content is visible."""
    candidates = [
        'button:has-text("知道了")',
        'button:has-text("我知道了")',
        'button:has-text("关闭")',
        'button:has-text("取消")',
        'button:has-text("Agree")',
        'button[aria-label="Close"]',
        '.close-btn',
        '.modal-close',
        '[class*="close" i]',
    ]
    for sel in candidates:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click(timeout=1500)
                logger.debug(f"dismissed overlay via {sel}")
                page.wait_for_timeout(500)
        except Exception:
            continue


def _fetch_one_target(ctx, page, url: str, wait_ms: int, kind: str,
                      limit: int, scrolls: int, logger) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=20000)
        status = resp.status if resp else None
        logger.info(f"GET {url} -> status={status}")
        if status and status >= 400:
            logger.warning(f"{url} returned HTTP {status}; recording but skipping parse")
            return out

        # Initial wait for SPA hydration
        page.wait_for_timeout(wait_ms)
        _dismiss_overlays(page, logger)

        # Random natural pause before scroll
        _human_sleep(0.4, 1.0)

        # Scroll to load more (only on lists / timelines, skip coin-rank which is single page)
        if kind in ("home", "timeline", "discover"):
            _scroll_for_more(page, logger, scrolls=scrolls, pause_s=random.uniform(0.8, 1.4))

        # Choose extractor
        if kind == "coin":
            raw = page.evaluate(EVALUATE_COIN_RANK_JS, limit)
        elif kind == "discover":
            raw = page.evaluate(EVALUATE_DISCOVERY_JS, limit)
        else:
            raw = page.evaluate(EVALUATE_TIMELINE_JS, limit)

        if not isinstance(raw, list):
            logger.warning(f"{url}: extractor returned non-list: {type(raw).__name__}")
            raw = []

        logger.info(f"{url}: extracted {len(raw)} raw cards")
        for card in raw:
            norm = _normalize_card(card, kind=kind, source_url=url)
            if norm:
                out.append(norm)
    except Exception as exc:
        logger.warning(f"fetch {url} failed: {exc}")
    return out


def _normalize_card(card: dict[str, Any], *, kind: str, source_url: str) -> dict[str, Any] | None:
    """Map a raw extractor dict into the standardized output schema."""
    if not isinstance(card, dict):
        return None
    href = card.get("href") or ""
    title = (card.get("title") or "").strip()
    body = (card.get("body") or "").strip()
    if not title and not body:
        return None
    if not href:
        return None

    # Stock symbol extraction: union of URL-based + cashtag-based
    symbols = _stock_symbols_from_url(href) + _stock_symbols_from_text(body) + _stock_symbols_from_text(title)
    symbols = list(dict.fromkeys(symbols))

    counts = card.get("counts") or {}
    if not isinstance(counts, dict):
        counts = {}

    # Derive summary (first 500 chars of body, stripping newlines)
    summary = " ".join(body.split())[:500]

    # Source tag
    if kind == "coin":
        src_tag = "xueqiu(热股)"
    elif kind == "discover":
        src_tag = "xueqiu(热门)"
    elif "today/people" in source_url:
        src_tag = "xueqiu(关注)"
    else:
        src_tag = "xueqiu(动态)"

    return {
        "title": title[:200],
        "url": href,
        "published_at": _now_iso(),  # timeline pages rarely expose absolute timestamps
        "summary": summary,
        "source": src_tag,
        "user": (card.get("author") or "").strip()[:60] or None,
        "reposts_count": int(counts.get("reposts") or 0),
        "comments_count": int(counts.get("comments") or 0),
        "likes_count": int(counts.get("likes") or 0),
        "views_count": int(counts.get("views") or 0),
        "stock_symbols": symbols,
        "raw_time_text": (card.get("time_text") or "").strip()[:80] or None,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--output", type=str, default="/data/xueqiu/today.json")
    ap.add_argument("--profile-dir", type=str, default=PROFILE_DIR)
    ap.add_argument("--no-trending", action="store_true")
    ap.add_argument("--no-timeline", action="store_true")
    ap.add_argument("--max-items", type=int, default=200)
    ap.add_argument("--verbose", action="store_true", help="debug-level logging")
    ap.add_argument(
        "--viewport-jitter",
        action="store_true",
        help="vary viewport size between requests (extra anti-bot signal)",
    )
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    global logger
    logger = logging.getLogger("xueqiu-playwright")

    profile = Path(args.profile_dir)
    if not profile.exists():
        logger.error(f"profile not found: {profile}")
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump({
                "source": SOURCE,
                "fetched_at": _now_iso(),
                "count": 0,
                "items": [],
                "login_state": "no_profile",
                "errors": [f"profile not found: {profile}"],
            }, f, ensure_ascii=False, indent=2)
        return 2

    out: list[dict[str, Any]] = []
    login_state = "unknown"
    errors: list[str] = []
    targets = list(URL_TARGETS)
    if args.no_trending:
        targets = [t for t in targets if t[2] != "coin"]
    if args.no_timeline:
        # Drop the homepage + today timeline; keep coin-rank + discovery (which is more "discovery" than timeline)
        targets = [t for t in targets if t[2] not in ("home", "timeline")]

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=True,
            viewport={"width": 1440, "height": 900},
            user_agent=UA,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            extra_http_headers={
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cache-Control": "no-cache",
            },
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        # Anti-bot: hide webdriver before any page script runs
        ctx.add_init_script(_anti_bot_init_script())

        page = ctx.new_page() if not ctx.pages else ctx.pages[0]

        # --- Verify login state ---
        try:
            resp = page.goto("https://xueqiu.com/", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)
            cookies = {c["name"] for c in ctx.cookies()}
            logger.info(f"cookie names: {sorted(cookies)[:15]}{'...' if len(cookies) > 15 else ''}")
            if any(n in cookies for n in ("u", "xq_a_token", "xqat", "xq_is_login", "xq_r_token", "xq_token")):
                login_state = "logged_in"
            else:
                login_state = "no_login_cookies"
            status = resp.status if resp else None
            logger.info(f"login_state={login_state}; status={status}; total cookies={len(cookies)}")
        except Exception as e:
            logger.warning(f"login check failed: {e}")
            login_state = "check_failed"
            errors.append(f"login check failed: {e}")

        # Optional: validate the cookie actually has access by hitting the protected /account/manage page
        if login_state == "logged_in":
            try:
                probe = page.goto("https://xueqiu.com/account/manage", wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(2000)
                probe_status = probe.status if probe else None
                if probe_status and probe_status >= 400:
                    logger.warning(f"/account/manage returned {probe_status}; cookie may be partially invalid")
                    errors.append(f"account/manage HTTP {probe_status}")
                    login_state = "cookie_rejected"
                else:
                    logger.info(f"/account/manage ok (status={probe_status})")
            except Exception as e:
                logger.warning(f"account/manage probe failed: {e}")
                errors.append(f"account/manage probe failed: {e}")

        # --- Run all URL targets ---
        if login_state in ("logged_in", "cookie_rejected"):
            # Even with cookie_rejected we try the public pages (xueqiu still
            # serves public timelines to logged-out callers).
            for url, wait_ms, kind, limit, scrolls in targets:
                if args.viewport_jitter:
                    try:
                        w = random.choice([1366, 1440, 1536, 1680])
                        h = random.choice([800, 900, 1000])
                        page.set_viewport_size({"width": w, "height": h})
                    except Exception:
                        pass
                _human_sleep(0.8, 1.6)
                items = _fetch_one_target(ctx, page, url, wait_ms, kind, limit, scrolls, logger)
                out.extend(items)
                logger.info(f"{url} contributed {len(items)} items (running total={len(out)})")
        else:
            logger.warning(f"login_state={login_state}; skipping fetch")

        try:
            ctx.close()
        except Exception:
            pass

    # Dedup by (url, title-prefix) and trim
    deduped: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for item in out:
        key = (item.get("url") or "") + "|" + (item.get("title") or "")[:60]
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(item)
        if len(deduped) >= args.max_items:
            break

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": SOURCE,
        "fetched_at": _now_iso(),
        "count": len(deduped),
        "items": deduped,
        "login_state": login_state,
        "errors": errors,
        "urls_attempted": [t[0] for t in targets],
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"wrote {len(deduped)} items to {args.output} (login_state={login_state})")
    return 0 if deduped else 2


if __name__ == "__main__":
    sys.exit(main())