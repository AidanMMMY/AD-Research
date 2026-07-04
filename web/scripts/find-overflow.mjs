import { chromium } from "playwright";

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 375, height: 812 } });
const page = await context.newPage();

await page.goto("http://localhost:5173/login", { waitUntil: "load" });
await page.fill('input[placeholder="用户名"]', "admin");
await page.fill('input[placeholder="密码"]', "kWZK*Ee*%sMZ3r-5");
await page.click('.login-submit');
await page.waitForURL(/\/dashboard/, { timeout: 15000 });
await page.waitForTimeout(2000);

const info = await page.evaluate(() => {
  const html = document.documentElement;
  const body = document.body;
  const offenders = [];
  const all = document.querySelectorAll("*");
  for (const el of all) {
    const rect = el.getBoundingClientRect();
    if (rect.right > html.clientWidth + 1 && rect.width > 0) {
      offenders.push({
        tag: el.tagName,
        class: typeof el.className === "string" ? el.className.slice(0, 80) : "",
        id: el.id,
        right: Math.round(rect.right),
        width: Math.round(rect.width),
        htmlWidth: html.clientWidth,
      });
    }
  }
  return {
    htmlScrollWidth: html.scrollWidth,
    htmlClientWidth: html.clientWidth,
    bodyScrollWidth: body.scrollWidth,
    offenders: offenders.slice(0, 20),
  };
});
console.log(JSON.stringify(info, null, 2));
await browser.close();
