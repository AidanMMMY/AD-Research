#!/usr/bin/env python3
"""warmup_social_profiles.py — one-shot manual login helper for shared Playwright profile.

Opens each platform in turn in a real (headed) Chromium, lets YOU log in
(X scan QR / type creds), waits for the auth cookie to appear, then closes
the browser. All platforms share a single profile directory so cookies are
reused by the agent workers.

Usage:
    pip install playwright
    playwright install chromium

    # Default: xueqiu + x + reddit
    python3 warmup_social_profiles.py

    # Pick a subset:
    python3 warmup_social_profiles.py --platforms xueqiu,x

    # Use a custom profile dir:
    python3 warmup_social_profiles.py --profile-dir ~/.playwright-profile-alloyresearch

After all platforms succeed:
    scp -r ~/.playwright-profile-alloyresearch root@<ECS>:/root/.playwright-profile/

Exit codes:
    0 = all platforms logged in successfully
    1 = timeout for one or more platforms
    2 = Playwright/browser error
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Callable

from playwright.sync_api import sync_playwright  # noqa: E402

DEFAULT_PROFILE_DIR = os.path.expanduser("~/.playwright-profile-alloyresearch")

# (name, login_url, cookie_names_to_check, post_login_url_to_verify, human_label)
PLATFORMS = [
    (
        "xueqiu",
        "https://xueqiu.com/",
        ["u", "acw_tc", "xq_a_token", "xqat"],  # 多种雪球 session cookie 名
        "https://xueqiu.com/account/manage",
        "雪球 (Xueqiu) - 扫码 or 账密",
    ),
    (
        "x",
        "https://x.com/i/flow/login",
        ["auth_token", "ct0", "gt"],
        "https://x.com/settings/account",
        "X / Twitter - 登录后停留在首页",
    ),
    (
        "reddit",
        "https://www.reddit.com/",
        ["reddit_session", "token_v2"],
        "https://www.reddit.com/inbox",
        "Reddit - 登录后停留在首页",
    ),
]


def wait_for_login(context, page, cookie_names: list[str], verify_url: str, timeout: int, log: Callable) -> bool:
    """Wait until either: any of the cookies appears AND the verify_url returns 200.

    Cookies alone are insufficient (e.g. Xueqiu legacy cookies survive logout).
    The URL probe is the source of truth.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        cookies = context.cookies()
        cookie_names_seen = {c.get("name") for c in cookies}
        if any(n in cookie_names_seen for n in cookie_names):
            # Cookie present, now verify by hitting the protected URL
            try:
                resp = page.goto(verify_url, wait_until="domcontentloaded", timeout=15000)
                if resp and resp.status == 200 and "/login" not in page.url and "flow/login" not in page.url:
                    return True
            except Exception:
                pass
        time.sleep(2)
    return False
    while time.time() < deadline:
        cookies = context.cookies()
        for c in cookies:
            if c.get("name") == cookie_name:
                return True
        time.sleep(2)
    return False


def login_one_platform(p, profile_dir: Path, timeout: int, log: Callable) -> bool:
    name, url, cookie_names, verify_url, human = p
    log(f"\n=== {human} ===")
    log(f"Opening {url} in a real Chromium ...")
    log("Please log in. Detecting login by waiting for any of: " + ", ".join(cookie_names))
    log(f"Plus probing: {verify_url} (must return 200 without redirecting to login).")
    log(f"Timeout: {timeout} seconds.\n")

    with sync_playwright() as p_pw:
        try:
            context = p_pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
        except Exception as exc:
            log(f"  ERROR launching browser: {exc}")
            return False

        page = context.new_page() if not context.pages else context.pages[0]
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            log(f"  WARN goto {url} failed: {exc} (continuing, you can navigate manually)")

        success = wait_for_login(context, page, cookie_names, verify_url, timeout, log)
        if success:
            log(f"  ✓ Login verified for {name} (cookie + protected URL accessible).")
        else:
            log(f"  ✗ Timed out after {timeout}s waiting for cookie `{cookie_name}`.")
            log("    (you can re-run this script later to retry this platform only)")

        try:
            context.close()
        except Exception:
            pass
        return success


def main():
    parser = argparse.ArgumentParser(description="Warm up social-media login profiles for ad-research agent workers")
    parser.add_argument(
        "--platforms",
        default="xueqiu,x,reddit",
        help="Comma-separated subset of: xueqiu,x,reddit (default: xueqiu,x,reddit)",
    )
    parser.add_argument(
        "--profile-dir",
        default=DEFAULT_PROFILE_DIR,
        help=f"Shared Playwright profile directory (default: {DEFAULT_PROFILE_DIR})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Per-platform login timeout in seconds (default: 300)",
    )
    args = parser.parse_args()

    profile_dir = Path(args.profile_dir).expanduser().resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    print(f"[warmup] profile_dir = {profile_dir}")

    requested = [p.strip() for p in args.platforms.split(",") if p.strip()]
    by_name = {p[0]: p for p in PLATFORMS}
    selected = [by_name[n] for n in requested if n in by_name]
    if not selected:
        print(f"  ERROR: no valid platforms in {args.platforms!r}. Valid: {[p[0] for p in PLATFORMS]}")
        sys.exit(2)
    print(f"[warmup] platforms to warm: {[p[0] for p in selected]}")

    results: dict[str, bool] = {}
    for p in selected:
        results[p[0]] = login_one_platform(p, profile_dir, args.timeout, print)
        if not results[p[0]]:
            user_input = input(f"  Continue to next platform? (y/N): ").strip().lower()
            if user_input != "y":
                break

    print("\n=== summary ===")
    for name, ok in results.items():
        print(f"  {name:10s} {'OK' if ok else 'FAIL'}")
    if all(results.values()):
        print(f"\nAll platforms logged in. Next:")
        print(f"  scp -r {profile_dir} root@<ECS>:/root/.playwright-profile/")
        sys.exit(0)
    else:
        failed = [n for n, ok in results.items() if not ok]
        print(f"\nFailed: {failed}. Re-run with --platforms {','.join(failed)} to retry.")
        sys.exit(1)


if __name__ == "__main__":
    main()
