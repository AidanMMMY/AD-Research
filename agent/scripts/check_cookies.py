import sqlite3
from pathlib import Path
from playwright.sync_api import sync_playwright

# Check the raw cookies file
cookies_path = Path("/profile/Default/Cookies")
print(f"Cookies file exists: {cookies_path.exists()}")
if cookies_path.exists():
    print(f"Size: {cookies_path.stat().st_size}")
    try:
        conn = sqlite3.connect(str(cookies_path))
        cur = conn.cursor()
        cur.execute("SELECT name, host_key, value FROM cookies ORDER BY host_key LIMIT 50")
        rows = cur.fetchall()
        print(f"SQLite sees {len(rows)} cookies:")
        for name, host, val in rows:
            print(f"  {host} | {name} = {val[:30]}...")
        conn.close()
    except Exception as e:
        print(f"SQLite read failed: {e}")

print("\n--- Playwright load ---")
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir="/profile",
        headless=True,
        viewport={"width": 1280, "height": 800},
    )
    cookies = ctx.cookies()
    print(f"Playwright sees {len(cookies)} cookies:")
    for c in cookies:
        print(f"  {c[domain]} | {c[name]} = {c[value][:20]}...")
    ctx.close()
