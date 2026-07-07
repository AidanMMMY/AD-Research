#!/usr/bin/env python3
"""Export all Playwright profile cookies (with values) to a JSON file.

macOS Chromium stores cookie values in Keychain, not in the SQLite file.
This script reads the actual cookie values via Playwright's API and dumps
them so they can be re-imported on Linux where Keychain is unavailable.
"""
import argparse
import json
import os
from playwright.sync_api import sync_playwright


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile-dir", default=os.path.expanduser("~/.playwright-profile-alloyresearch"))
    ap.add_argument("--output", default=os.path.expanduser("~/.playwright-profile-alloyresearch.cookies.json"))
    args = ap.parse_args()

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=args.profile_dir,
            headless=True,
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        cookies = ctx.cookies()
        ctx.close()

    # Strip non-serializable fields
    safe = []
    for c in cookies:
        safe.append({
            "name": c["name"],
            "value": c["value"],
            "domain": c["domain"],
            "path": c.get("path", "/"),
            "expires": c.get("expires", -1),
            "httpOnly": c.get("httpOnly", False),
            "secure": c.get("secure", False),
            "sameSite": c.get("sameSite", "None"),
        })

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(safe, f, ensure_ascii=False, indent=2)
    print(f"Exported {len(safe)} cookies to {args.output}")
    for c in safe:
        v = c["value"][:30] + "..." if len(c["value"]) > 30 else c["value"]
        print(f"  {c['domain']:30s} | {c['name']:25s} = {v}")


if __name__ == "__main__":
    main()
