import asyncio
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir="/profile",
        headless=True,
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    )
    page = ctx.new_page()
    page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)
    url = page.url
    text = page.locator("body").inner_text()[:500]
    print(f"X /home url: {url}")
    has_username = "@Aidan" in text
    print(f"has @Aidan username: {has_username}")
    print(f"text snippet: {text[:300]}")
    ctx.close()
