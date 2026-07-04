#!/usr/bin/env node
/**
 * Phase 7 ECS production validation — single theme desktop.
 *
 * Most conservative variant: one viewport, one theme, with long delays
 * between navigations to avoid ECS/nginx rate-limit resets.
 *
 * Usage:
 *   cd web && BASE_URL=http://47.239.13.111:8000 node scripts/visual-regression-ecs-single.mjs
 */
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const BASE_URL = process.env.BASE_URL || "http://47.239.13.111:8000";
const ADMIN_USER = process.env.ADMIN_USER || "admin";
const ADMIN_PASS = process.env.ADMIN_PASS || "kWZK*Ee*%sMZ3r-5";
const OUT_DIR = path.resolve(process.cwd(), "screenshots", "phase7-ecs");

const PAGES = [
  { path: "/login", name: "login", auth: false },
  { path: "/dashboard", name: "dashboard", auth: true },
  { path: "/instruments", name: "instrument-list", auth: true },
  { path: "/instruments/AAPL", name: "instrument-detail", auth: true },
  { path: "/screen", name: "screen", auth: true },
  { path: "/ai-chat", name: "ai-chat", auth: true },
  { path: "/admin/deployments", name: "admin-deployments", auth: true },
];

function waitForServer(url, timeoutMs = 120_000) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const probe = async () => {
      try {
        const res = await fetch(url);
        if (res.status === 200 || res.status === 304) {
          resolve();
          return;
        }
      } catch {
        // retry
      }
      if (Date.now() - start > timeoutMs) {
        reject(new Error(`Server ${url} did not become ready in ${timeoutMs}ms`));
        return;
      }
      setTimeout(probe, 1000);
    };
    probe();
  });
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true });
  await waitForServer(`${BASE_URL}/health`);
  console.log(`ECS backend ready at ${BASE_URL}`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();

  const results = [];

  try {
    // Login once, then set theme.
    await page.goto(`${BASE_URL}/login`, { waitUntil: "load" });
    await page.evaluate(() => {
      localStorage.setItem("ad-research-theme", "light");
      localStorage.setItem("ad-research-color-convention", "china");
      localStorage.setItem("ad-research-onboarding-storage", JSON.stringify({ state: { completed: true }, version: 0 }));
    });
    await page.fill('input[placeholder="用户名"]', ADMIN_USER);
    await page.fill('input[placeholder="密码"]', ADMIN_PASS);
    await page.click('.login-submit');
    await page.waitForURL(/\/(dashboard|instruments)/, { timeout: 15_000 });
    await page.reload({ waitUntil: "load" });
    await page.waitForTimeout(1500);

    for (const pageDef of PAGES) {
      try {
        await page.goto(`${BASE_URL}${pageDef.path}`, { waitUntil: "load" });
        await page.waitForTimeout(2500);

        const fileName = `${pageDef.name}__light__desktop.png`;
        const filePath = path.join(OUT_DIR, fileName);
        await page.screenshot({ path: filePath, fullPage: true });

        const consoleErrors = [];
        const handler = (msg) => {
          if (msg.type() === "error") consoleErrors.push(msg.text());
        };
        page.on("console", handler);
        // Give console events a moment to arrive.
        await page.waitForTimeout(500);
        page.off("console", handler);

        const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
        const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
        const overflowX = scrollWidth > clientWidth ? scrollWidth - clientWidth : 0;

        results.push({ fileName, consoleErrors: consoleErrors.length, overflowX, page: pageDef.name });
        console.log(`✓ ${fileName} (errors=${consoleErrors.length}, overflowX=${overflowX}px)`);
      } catch (err) {
        console.error(`✗ ${pageDef.name}: ${err.message}`);
        results.push({ fileName: "-", consoleErrors: 0, overflowX: 0, page: pageDef.name, error: err.message });
      }
      // Long delay between pages to avoid ECS rate limits.
      await page.waitForTimeout(10000);
    }
  } finally {
    await context.close();
    await browser.close();
  }

  const total = results.length;
  const errors = results.filter((r) => r.consoleErrors > 0).length;
  const overflows = results.filter((r) => r.overflowX > 0).length;
  const failures = results.filter((r) => r.error).length;

  console.log("\n=== Phase 7 ECS Single-Theme Desktop Validation Summary ===");
  console.log(`Base URL: ${BASE_URL}`);
  console.log(`Screenshots: ${total} (${OUT_DIR})`);
  console.log(`Pages with console errors: ${errors}`);
  console.log(`Pages with horizontal overflow: ${overflows}`);
  console.log(`Failed captures: ${failures}`);

  if (failures > 0) {
    process.exitCode = 1;
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
