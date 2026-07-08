#!/usr/bin/env python3
"""cls.py - 财联社快讯 worker (CLS flash-news fetcher).

Architecture (2026-07 rewrite)
------------------------------
CloudWAF now blocks the legacy ``/nodeapi/updateTelegraphList`` endpoint and
the ``requests`` library TLS fingerprint (both 404 + WAF). The CLS public site
is a Next.js SPA at https://www.cls.cn/telegraph whose internal data fetch is
``/api/cache?name=telegraph&rn=20`` (snapshot of latest 20 telegraphs) plus a
signed ``/v1/roll/get_roll_list`` (errno 10012 = signature error without
``sv`` / ``sign`` params).

Strategy
~~~~~~~~
1. Try ``/api/cache`` with curl_cffi impersonating chrome124 (and the rest of
   the profile list). This returns up to 20 items per call. Confirmed working
   on the ECS IP 2026-07-07 against every impersonate profile below.
2. Optionally probe ``/v1/roll/get_roll_list`` with ``refresh_type=1&rn=20``
   just to record the errno for diagnostics — it always returns errno 10012
   (signed) on this network so we don't keep retrying it.
3. If curl_cffi is unavailable or every profile is blocked, fall back to
   Playwright (real headless Chrome, profile at /profile) — but only if the
   browser binary is present, otherwise fail gracefully.
4. Otherwise write an empty array and exit 2 (orchestrator marks this worker
   as "blocked by upstream WAF" rather than fatal).

Self-contained: does NOT import common.py (per task constraint). Output JSON
schema:

    {
      "source": "财联社",
      "fetched_at": "2026-07-07T08:30:00Z",
      "count": 20,
      "items": [
        {
          "title": "...",
          "url": "https://www.cls.cn/detail/1234567",
          "published_at": "2026-07-07T08:25:14Z",
          "summary": "...",
          "source": "财联社",
          "method_attempted": "curl_cffi/chrome124",
          "login_state": "anonymous"
        }
      ]
    }

Usage:
    python cls.py --hours 24 --output /data/cls/today.json
    python cls.py --hours 24 --output /data/cls/today.json --impersonate chrome124
    python cls.py --hours 24 --output /data/cls/today.json --verbose
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG = logging.getLogger("ad-research.cls")

SOURCE = "财联社"

UA_CHROME = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
UA_SAFARI = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1"
)
UA_EDGE = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 "
    "Safari/537.36 Edg/124.0.0.0"
)

# curl_cffi 0.15 BrowserType profile names (cross-checked at runtime)
IMPERSONATE_PROFILES = [
    "chrome124",
    "chrome120",
    "chrome119",
    "chrome116",
    "safari172_ios",
    "edge101",
]

# Endpoints (in priority order). All under the same TLS fingerprint regime.
CACHE_ENDPOINT = "https://www.cls.cn/api/cache"
ROLL_ENDPOINT = "https://www.cls.cn/v1/roll/get_roll_list"
TELEGRAPH_HTML = "https://www.cls.cn/telegraph"
HOME_HTML = "https://www.cls.cn/"

CACHE_PARAMS_BASE = {
    "name": "telegraph",
    "rn": "20",
}
ROLL_PARAMS_BASE = {
    "refresh_type": "1",
    "rn": "20",
    "last_time": "0",
}


# ---------------------------------------------------------------------------
# Helpers (no common.py dependency)
# ---------------------------------------------------------------------------
def _iso_utc(ts: Any) -> str | None:
    if ts is None:
        return None
    try:
        v = float(ts)
        if v > 1e11:  # ms
            v = v / 1000.0
        return datetime.fromtimestamp(v, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return str(ts) if ts else None


def _truncate(text: str, n: int) -> str:
    if not text:
        return ""
    s = str(text).strip()
    return s if len(s) <= n else s[: max(0, n - 1)].rstrip() + "..."


def _ua_for(profile: str) -> str:
    if profile.startswith("safari"):
        return UA_SAFARI
    if profile.startswith("edge"):
        return UA_EDGE
    return UA_CHROME


def _configure_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _write_output(path: str | None, items: list, *,
                  source: str = SOURCE,
                  method_attempted: str = "",
                  login_state: str = "anonymous") -> str:
    if not items:
        items = []
    for it in items:
        it.setdefault("source", source)
        it.setdefault("method_attempted", method_attempted)
        it.setdefault("login_state", login_state)
    out_path = path or "/data/ad-research/cls/today.json"
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": source,
        "fetched_at": datetime.now(tz=timezone.utc)
            .isoformat(timespec="seconds").replace("+00:00", "Z"),
        "count": len(items),
        "method_attempted": method_attempted,
        "login_state": login_state,
        "items": items,
    }
    tmp = Path(out_path).with_suffix(Path(out_path).suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(out_path)
    LOG.info("wrote %d items to %s (%d bytes)",
             payload["count"], out_path, Path(out_path).stat().st_size)
    # one-line summary to stdout for the orchestrator
    print(json.dumps({"source": source,
                      "count": payload["count"],
                      "path": out_path,
                      "method": method_attempted}))
    return out_path


def _normalize(item: dict, *, default_url: str) -> dict | None:
    title = (item.get("title") or "").strip()
    content = (item.get("content") or item.get("brief") or "").strip()
    if not title and not content:
        return None
    display_title = title or _truncate(content, 80)
    summary = content if content else display_title
    item_id = item.get("id")
    if item_id:
        url = f"https://www.cls.cn/detail/{item_id}"
    else:
        shareurl = item.get("shareurl") or item.get("url") or ""
        if shareurl and not shareurl.startswith("http"):
            shareurl = f"https://www.cls.cn{shareurl}"
        url = shareurl or default_url
    return {
        "title": display_title,
        "url": url,
        "published_at": _iso_utc(item.get("ctime") or item.get("showtime")),
        "summary": _truncate(summary, 500),
        "source": SOURCE,
    }


def _parse_cache_payload(payload: Any, *, default_url: str) -> list[dict]:
    """Parse /api/cache response: { errno, data: { roll_data: [...] } }."""
    if not isinstance(payload, dict):
        return []
    if payload.get("errno") not in (0, "0", None):
        LOG.warning("cache payload errno=%s msg=%s",
                    payload.get("errno"), payload.get("msg"))
        return []
    data = payload.get("data") or {}
    roll = data.get("roll_data") or data.get("items") or []
    out: list[dict] = []
    for r in roll:
        rec = _normalize(r, default_url=default_url)
        if rec:
            out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Strategy 1: curl_cffi + /api/cache
# ---------------------------------------------------------------------------
def _build_session(impersonate: str):
    from curl_cffi import requests as cffi_requests
    sess = cffi_requests.Session()
    sess.headers.update({
        "User-Agent": _ua_for(impersonate),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.cls.cn/telegraph",
        "Origin": "https://www.cls.cn",
    })
    return sess


def _probe_with_curl_cffi(profile: str, *, timeout: int,
                          rn: int = 20) -> tuple[str, str, list[dict]]:
    """Single attempt: GET /api/cache?rn=N&name=telegraph with one profile.

    Returns (status_label, method_attempted, items).
        status_label: "ok" | "blocked" | "signed" | "error:<name>"
    """
    method = f"curl_cffi/{profile}"
    try:
        sess = _build_session(profile)
        params = dict(CACHE_PARAMS_BASE)
        params["rn"] = str(rn)
        r = sess.get(CACHE_ENDPOINT, params=params,
                     impersonate=profile, timeout=timeout)
        if r.status_code in (403, 503):
            return "blocked", method, []
        if r.status_code != 200:
            return f"http_{r.status_code}", method, []
        try:
            payload = r.json()
        except ValueError:
            LOG.warning("non-JSON body (%d bytes) on %s",
                        len(r.text), profile)
            return "non_json", method, []
        items = _parse_cache_payload(payload, default_url=TELEGRAPH_HTML)
        if items:
            return "ok", method, items
        return "empty", method, []
    except Exception as e:  # noqa: BLE001
        LOG.warning("curl_cffi/%s failed: %s: %s",
                    profile, type(e).__name__, e)
        return f"error:{type(e).__name__}", method, []


def _probe_signed_endpoint(profile: str, *, timeout: int) -> str:
    """One diagnostic call to /v1/roll/get_roll_list to record errno."""
    try:
        sess = _build_session(profile)
        r = sess.get(ROLL_ENDPOINT, params=ROLL_PARAMS_BASE,
                     impersonate=profile, timeout=timeout)
        if r.status_code == 200:
            try:
                d = r.json()
                return f"errno={d.get('errno')} msg={d.get('msg')}"
            except ValueError:
                return f"http_{r.status_code}_nonjson"
        return f"http_{r.status_code}"
    except Exception as e:  # noqa: BLE001
        return f"error:{type(e).__name__}"


def collect_curl_cffi(*, profiles: list[str], timeout: int, max_items: int,
                      rate: float, also_probe_signed: bool) -> tuple[list[dict], str]:
    """Try each profile in order, return (items, method_used)."""
    attempts = []
    for prof in profiles:
        LOG.info("trying /api/cache with impersonate=%s (rn=%d)",
                 prof, max_items)
        status, method, items = _probe_with_curl_cffi(
            prof, timeout=timeout, rn=max_items)
        attempts.append((prof, status, len(items)))
        if items:
            LOG.info("OK: %d items via %s (status=%s)",
                     len(items), method, status)
            return items[:max_items], method
        # If the signed endpoint hasn't been probed yet, do it once for
        # diagnostics (cheap; errno is consistent across profiles).
        if also_probe_signed:
            LOG.info("probing signed %s: %s",
                     ROLL_ENDPOINT, _probe_signed_endpoint(prof, timeout=timeout))
            also_probe_signed = False
        LOG.info("no data via %s (status=%s)", method, status)
        if rate > 0:
            time.sleep(rate)
    LOG.warning("curl_cffi: all %d profiles returned no data; attempts=%s",
                len(profiles), attempts)
    return [], "curl_cffi/all_failed"


# ---------------------------------------------------------------------------
# Strategy 2: Playwright fallback (real headless Chrome)
# ---------------------------------------------------------------------------
def collect_playwright(*, hours: int, timeout: int, headless: bool) -> tuple[list[dict], str]:
    """Use Playwright Chromium to render the SPA, then extract telegraph nodes.

    This is slow (~10-20s) but is the last resort when curl_cffi is blocked.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        LOG.warning("playwright not installed; skipping fallback")
        return [], "playwright/not_installed"

    user_data_dir = os.environ.get("PLAYWRIGHT_USER_DATA_DIR", "/profile")
    profile_method = f"playwright/Chromium (profile={user_data_dir})"

    items: list[dict] = []
    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=headless,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
            except Exception as e:
                LOG.warning("launch_persistent_context failed (%s); "
                            "trying bare launch", e)
                browser = pw.chromium.launch(headless=headless,
                                             args=["--no-sandbox"])
                context = browser.new_context()
            else:
                context = browser

            page = context.new_page() if hasattr(context, "new_page") else context.pages[0]
            LOG.info("navigating to %s", TELEGRAPH_HTML)
            page.goto(TELEGRAPH_HTML, wait_until="domcontentloaded",
                      timeout=timeout * 1000)
            # Wait for SPA to populate; CLS renders telegraphs into .telegraph-content-br-*
            try:
                page.wait_for_selector(
                    "[class*='telegraph-content-br-'], [class*='telegraph-vip-content']",
                    timeout=timeout * 1000,
                )
            except Exception as e:
                LOG.warning("telegraph selector wait timed out: %s", e)

            # Scroll a bit to trigger lazy load
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)
            except Exception:
                pass

            html = page.content()
            Path("/data/ad-research/cls/_playwright_telegraph.html") \
                .parent.mkdir(parents=True, exist_ok=True)
            with open("/data/ad-research/cls/_playwright_telegraph.html",
                      "w", encoding="utf-8") as f:
                f.write(html)

            # Extract items from rendered DOM. The SPA uses class names like
            # 'telegraph-content-br-close' for each telegraph entry; the title
            # is in a sibling element with the actual text. As a robust
            # fallback, look for any JSON state dump in the page.
            # Strategy A: extract embedded __NEXT_DATA__ + page state.
            try:
                state = page.evaluate(
                    "() => window.__NEXT_DATA__ ? JSON.stringify(window.__NEXT_DATA__) : null"
                )
            except Exception:
                state = None
            if state:
                try:
                    d = json.loads(state)
                    props = (d.get("props") or {}).get("pageProps") or {}
                    init = props.get("initialState") or {}
                    arr = init.get("telegraphList") or init.get("items") or []
                    for raw in arr:
                        rec = _normalize(raw, default_url=TELEGRAPH_HTML)
                        if rec:
                            items.append(rec)
                except Exception as e:
                    LOG.debug("__NEXT_DATA__ parse failed: %s", e)

            # Strategy B: scrape the rendered HTML for telegraph IDs
            if not items:
                import re
                ids = re.findall(r'detail/(\d+)', html)
                briefs = re.findall(r'<[^>]*class="[^"]*telegraph[^"]*"[^>]*>([^<]{8,400})',
                                    html)
                seen = set()
                for i, bid in enumerate(ids):
                    if bid in seen:
                        continue
                    seen.add(bid)
                    brief = briefs[i] if i < len(briefs) else ""
                    items.append({
                        "title": _truncate(brief, 80) if brief else f"电报 #{bid}",
                        "url": f"https://www.cls.cn/detail/{bid}",
                        "published_at": _iso_utc(None),
                        "summary": _truncate(brief, 500),
                        "source": SOURCE,
                    })
                LOG.info("scraped %d telegraph IDs from rendered DOM", len(items))

            try:
                context.close()
            except Exception:
                pass
    except Exception as e:  # noqa: BLE001
        LOG.warning("playwright fallback failed: %s: %s",
                    type(e).__name__, e)
        return [], f"playwright/error:{type(e).__name__}"

    # Filter by hours
    cutoff_ts = time.time() - hours * 3600 if hours > 0 else None
    if cutoff_ts is not None:
        filtered = []
        for it in items:
            ts = it.get("published_at")
            if not ts:
                filtered.append(it)
                continue
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.timestamp() >= cutoff_ts:
                    filtered.append(it)
            except ValueError:
                filtered.append(it)
        items = filtered

    return items, profile_method


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch CLS (财联社) flash news")
    p.add_argument("--hours", type=int, default=24,
                   help="time window in hours (default: 24)")
    p.add_argument("--output", type=str, default=None,
                   help="output JSON path (default: /data/ad-research/cls/today.json)")
    p.add_argument("--data-root", type=str, default="/data/ad-research",
                   help="data root directory")
    p.add_argument("--limit", "--max-items", type=int, default=20, dest="max_items",
                   help="max items to keep (default: 20 = /api/cache page size)")
    p.add_argument("--timeout", type=int, default=20,
                   help="HTTP timeout seconds (default: 20)")
    p.add_argument("--rate", type=float, default=0.5,
                   help="seconds between HTTP retries (default: 0.5)")
    p.add_argument("--impersonate", "-i", default=None,
                   help="single impersonate profile (overrides default list)")
    p.add_argument("--no-playwright", action="store_true",
                   help="disable Playwright fallback")
    p.add_argument("--playwright-only", action="store_true",
                   help="skip curl_cffi, use Playwright directly")
    p.add_argument("--no-signed-probe", action="store_true",
                   help="skip the diagnostic signed-endpoint probe")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="verbose logging")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    _configure_logging(args.verbose)

    if args.output is None:
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        args.output = os.path.join(args.data_root, "cls", f"{ts}.json")

    profiles = ([args.impersonate] if args.impersonate
                else IMPERSONATE_PROFILES)
    also_probe = not args.no_signed_probe

    items: list[dict] = []
    method = "none"

    if not args.playwright_only:
        try:
            import curl_cffi  # noqa: F401  (smoke check)
        except ImportError:
            LOG.warning("curl_cffi not installed; jumping to Playwright fallback")
        else:
            items, method = collect_curl_cffi(
                profiles=profiles,
                timeout=args.timeout,
                max_items=args.max_items,
                rate=args.rate,
                also_probe_signed=also_probe,
            )

    if not items and not args.no_playwright:
        LOG.info("curl_cffi returned nothing; trying Playwright fallback")
        items, method = collect_playwright(
            hours=args.hours, timeout=args.timeout, headless=True)

    if not items:
        LOG.warning("no items collected; writing empty output and exiting 2")
        _write_output(args.output, [], source=SOURCE,
                      method_attempted=method, login_state="anonymous")
        return 2

    _write_output(args.output, items, source=SOURCE,
                  method_attempted=method, login_state="anonymous")
    return 0


if __name__ == "__main__":
    sys.exit(main())