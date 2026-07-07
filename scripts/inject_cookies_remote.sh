#!/bin/bash
set -e
scp /Users/aidanliu/.playwright-profile-alloyresearch.cookies.json ad-research:/root/.playwright-profile-alloyresearch.cookies.json
echo "Cookie file uploaded"

ssh ad-research << 'SSHEOF'
set -e
# Clear stale profile
rm -rf /root/.playwright-profile
mkdir -p /root/.playwright-profile
chmod 700 /root/.playwright-profile

cat > /root/ad-research/agent/scripts/inject_cookies.py << 'PYEOF'
import argparse, json
from pathlib import Path
from playwright.sync_api import sync_playwright
ap = argparse.ArgumentParser()
ap.add_argument("--profile-dir", default="/profile")
ap.add_argument("--cookies-json", default="/cookies.json")
args = ap.parse_args()
profile = Path(args.profile_dir)
print(f"Loading profile: {profile}")
with open(args.cookies_json) as f:
    cookies = json.load(f)
print(f"Injecting {len(cookies)} cookies...")
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=str(profile),
        headless=True,
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    )
    ctx.clear_cookies()
    ctx.add_cookies(cookies)
    page = ctx.new_page()
    for c in cookies:
        try:
            page.goto(f"https://{c['domain'].lstrip('.')}/", wait_until="domcontentloaded", timeout=10000)
            break
        except Exception:
            continue
    page.wait_for_timeout(3000)
    after = ctx.cookies()
    print(f"After injection: {len(after)} cookies present")
    for c in after:
        if c["name"] in ("auth_token", "ct0", "twid", "u", "xq_a_token", "reddit_session", "token_v2"):
            print(f"  {c['domain']:25s} | {c['name']:18s} = {c['value'][:25]}...")
    ctx.close()
print("Done. Cookies persisted.")
PYEOF

docker run --rm \
  --network alloyresearch-agent-network \
  -v /root/.playwright-profile:/profile:rw \
  -v /root/.playwright-profile-alloyresearch.cookies.json:/cookies.json:ro \
  -v /root/ad-research/agent/scripts:/workspace/scripts:ro \
  -e PLAYWRIGHT_USER_DATA_DIR=/profile \
  -e PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
  alloyresearch-agent:latest \
  python3 /workspace/scripts/inject_cookies.py --profile-dir /profile --cookies-json /cookies.json
SSHEOF
