#!/usr/bin/env python3
"""
xueqiu_warmup.py - one-shot manual login helper for the shared Playwright profile.

Purpose:
  The xueqiu_hot worker needs an authenticated `u` cookie to bypass XUEQIU's
  anti-bot challenges. This script opens xueqiu.com in a real (headed) browser,
  lets YOU scan the QR code / type credentials, waits for the `u` cookie to
  appear, then exits. The browser profile persists at PROFILE_DIR so the worker
  re-uses the cookie on every subsequent run.

Usage (pick ONE of three modes):

  -- MODE A: X virtual framebuffer on ECS (no display server required) ----
  # On ECS (Aliyun), inside an X-capable shell:
  cd /root/ad-research/agent
  xvfb-run -a python scripts/xueqiu_warmup.py
  # A Chromium window will appear in the virtual display. VNC into the
  # framebuffer with:  ssh -L 5900:localhost:5900 root@ecs
  #                    x11vnc -display :99 -nopw -forever    # in another shell
  #                    open vnc://localhost:5900             # on your Mac

  -- MODE B: VNC/X11 into the ECS container -------------------------------
  # On ECS:
  apt-get install -y x11vnc xvfb    # one-time
  export DISPLAY=:99
  Xvfb :99 -screen 0 1280x800x24 &
  x11vnc -display :99 -nopw -forever &
  python scripts/xueqiu_warmup.py
  # On your Mac: open Screen Sharing / VNC Viewer -> vnc://<ecs-public-ip>:5900

  -- MODE C: Run on your local Mac, then sync the profile back to ECS -----
  # On your Mac (with DISPLAY=:0 and a real browser window):
  PROFILE_DIR=~/.playwright-profile-xueqiu python scripts/xueqiu_warmup.py
  # Then SCP the profile up:
  scp -r ~/.playwright-profile-xueqiu root@<ecs>:/root/.playwright-profile/

After a successful login:
  - /root/.playwright-profile/Default/Cookies contains the `u` cookie.
  - /root/.playwright-profile/Local Storage/ contains session tokens.
  - The xueqiu_hot worker will then run authenticated for ~7-14 days until the
    cookie expires; just re-run this script when auth fails.

Exit codes:
  0 = login detected, cookies saved
  1 = timeout (no login within --timeout seconds)
  2 = Playwright / browser launch error
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

PROFILE_DIR_DEFAULT = "/root/.playwright-profile"
XUEQIU_HOME = "https://xueqiu.com/"
XUEQIU_LOGIN_PAGE = "https://xueqiu.com/account/login"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--profile-dir",
        type=str,
        default=os.environ.get("PROFILE_DIR", PROFILE_DIR_DEFAULT),
        help=f"Playwright persistent context dir (default: {PROFILE_DIR_DEFAULT}; "
             f"override via PROFILE_DIR env var, e.g. for Mode C).",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Seconds to wait for login before giving up (default: 600).",
    )
    p.add_argument(
        "--check-interval",
        type=int,
        default=3,
        help="Seconds between cookie checks (default: 3).",
    )
    p.add_argument(
        "--url",
        type=str,
        default=XUEQIU_HOME,
        help=f"Initial URL to open (default: {XUEQIU_HOME}).",
    )
    p.add_argument(
        "--headless",
        action="store_true",
        help="Run headless (NOT recommended - login requires a real browser UI).",
    )
    return p.parse_args()


def _has_u_cookie(context) -> bool:
    """True once xueqiu has set the `u` auth cookie on our context."""
    try:
        cookies = context.cookies()
    except Exception:
        return False
    for c in cookies:
        if c.get("name") == "u" and c.get("domain", "").endswith("xueqiu.com"):
            return True
    return False


def _homepage_has_username(page) -> bool:
    """Secondary signal: xueqiu home shows the user's nickname when logged in."""
    try:
        # Logged-in xueqiu shows a username link in the top nav.
        return page.locator("a[href^='/u/']").count() > 0
    except Exception:
        return False


def main() -> int:
    args = parse_args()
    profile_dir = Path(args.profile_dir).expanduser().resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright is not installed. Run: pip install playwright && playwright install chromium", file=sys.stderr)
        return 2

    print(f"[xueqiu_warmup] profile_dir = {profile_dir}", flush=True)
    print(f"[xueqiu_warmup] opening {args.url} in headed Chromium ...", flush=True)
    print(f"[xueqiu_warmup] >>> please scan QR / type credentials in the browser window <<<", flush=True)

    deadline = time.monotonic() + args.timeout
    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=args.headless,
                viewport={"width": 1280, "height": 900},
                locale="zh-CN",
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            )

            # If a page is already open (persistent context re-use), reuse it.
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(args.url, wait_until="domcontentloaded", timeout=30000)

            # If we landed on the login page automatically, that's fine - user
            # will interact with it. Otherwise, navigate.
            if "login" not in page.url.lower():
                try:
                    page.goto(XUEQIU_LOGIN_PAGE, wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    pass

            print(f"[xueqiu_warmup] current URL: {page.url}", flush=True)
            print(f"[xueqiu_warmup] polling for `u` cookie (timeout {args.timeout}s) ...", flush=True)

            while time.monotonic() < deadline:
                if _has_u_cookie(context):
                    print("[xueqiu_warmup] detected `u` cookie, login successful.", flush=True)
                    break
                if _homepage_has_username(page):
                    print("[xueqiu_warmup] detected username in nav, login successful.", flush=True)
                    break
                time.sleep(args.check_interval)
            else:
                print(f"[xueqiu_warmup] TIMEOUT after {args.timeout}s, no login detected.", file=sys.stderr, flush=True)
                context.close()
                return 1

            # Persist state to disk before exit.
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            context.close()

    except Exception as exc:
        print(f"[xueqiu_warmup] Playwright error: {exc}", file=sys.stderr, flush=True)
        return 2

    print(f"[xueqiu_warmup] 登录成功,cookie 已保存到 {profile_dir}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())