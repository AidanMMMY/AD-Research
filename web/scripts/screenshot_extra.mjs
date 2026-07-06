import { chromium } from 'playwright';
import path from 'path';

const BASE_URL = 'http://47.239.13.111:8000';
const OUT_DIR = '/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/screenshots/phase7-ecs';
const ADMIN_PASS = 'kWZK*Ee*%sMZ3r-5';

const PAGES = [
  '/global',
  '/sector-rotation',
  '/correlation',
  '/comparison',
  '/research',
  '/pools/1',
  '/instruments/300308.SZ',
];

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'load' });
  await page.fill('input[placeholder="用户名"]', 'admin');
  await page.fill('input[placeholder="密码"]', ADMIN_PASS);
  await page.click('.login-submit');
  await page.waitForURL(/\/(dashboard|instruments)/, { timeout: 15000 });
  
  for (const p of PAGES) {
    try {
      await page.goto(`${BASE_URL}${p}`, { waitUntil: 'load' });
      await page.waitForTimeout(2500);
      const name = p.replace(/\//g, '_').replace(/^_/, '').replace(/_$/, '') || 'root';
      await page.screenshot({ path: path.join(OUT_DIR, `extra__${name}.png`), fullPage: true });
      console.log(`✓ ${p}`);
    } catch (e) {
      console.error(`✗ ${p}: ${e.message}`);
    }
    await page.waitForTimeout(5000);
  }
  await browser.close();
})();
