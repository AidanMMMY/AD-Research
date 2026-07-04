#!/usr/bin/env node
/**
 * Phase 7 ECS production validation — desktop only.
 *
 * ECS public endpoint appears to rate-limit aggressive browser automation,
 * so this variant validates only the primary desktop viewport (3 themes)
 * with generous throttling. Tablet/mobile were already validated locally.
 *
 * Usage:
 *   cd web && BASE_URL=http://47.239.13.111:8000 node scripts/visual-regression-ecs-desktop.mjs
 */
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const BASE_URL = process.env.BASE_URL || "http://47.239.13.111:8000";
const ADMIN_USER = process.env.ADMIN_USER || "admin";
const ADMIN_PASS = process.env.ADMIN_PASS || "kWZK*Ee*%sMZ3r-5";
const OUT_DIR = path.resolve(process.cwd(), "screenshots", "phase7-ecs");

const VIEWPORT = { name: "desktop", width: 1280, height: 800 };

const PAGES = [
  { path: "/dashboard", name: "dashboard", auth: true },
  { path: "/instruments", name: "instrument-list", auth: true },
  { path: "/instruments/AAPL", name: "instrument-detail", auth: true },
  { path: "/screen", name: "screen", auth: true },
  { path: "/ai-chat", name: "ai-chat", auth: true },
  { path: "/admin/deployments", name: "admin-deployments", auth: true },
  { path: "/login", name: "login", auth: false },
];

const THEMES = [
  { name: "light", theme: "light", convention: "china" },
  { name: "dark", theme: "dark", convention: "china" },
  { name: "light-us", theme: "light", convention: "us" },
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

async function login(page) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: "load" });
  await page.fill('input[placeholder="用户名"]', ADMIN_USER);
  await page.fill('input[placeholder="密码"]', ADMIN_PASS);
  await page.click('.login-submit');
  await page.waitForURL(/\/(dashboard|instruments)/, { timeout: 15_000 });
}

async function applyTheme(page, themeDef) {
  await page.evaluate(
    ({ theme, convention }) => {
      localStorage.setItem("ad-research-theme", theme);
      localStorage.setItem("ad-research-color-convention", convention);
      localStorage.setItem("ad-research-onboarding-storage", JSON.stringify({ state: { completed: true }, version: 0 }));
    },
    { theme: themeDef.theme, convention: themeDef.convention }
  );
  await page.reload({ waitUntil: "load" });
  await page.waitForTimeout(1200);
}

async function capturePage(page, pageDef) {
  const consoleErrors = [];
  const handler = (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(msg.text());
    }
  };
  page.on("console", handler);

  await page.goto(`${BASE_URL}${pageDef.path}`, { waitUntil: "load" });
  await page.waitForTimeout(2000);

  const fileName = `${pageDef.name}__${pageDef.themeName}__desktop.png`;
  const filePath = path.join(OUT_DIR, fileName);
  await page.screenshot({ path: filePath, fullPage: true });

  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
  const overflowX = scrollWidth > clientWidth ? scrollWidth - clientWidth : 0;

  page.off("console", handler);
  return {
    fileName,
    consoleErrors: consoleErrors.length,
    overflowX,
  };
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true });
  await waitForServer(`${BASE_URL}/health`);
  console.log(`ECS backend ready at ${BASE_URL}`);

  const browser = await chromium.launch({ headless: true });
  const results = [];

  try {
    for (const themeDef of THEMES) {
      const context = await browser.newContext({
        viewport: { width: VIEWPORT.width, height: VIEWPORT.height },
        deviceScaleFactor: 1,
      });
      const page = await context.newPage();

      await page.goto(`${BASE_URL}/login`, { waitUntil: "load" });
      await page.evaluate(() => {
        localStorage.setItem("ad-research-onboarding-storage", JSON.stringify({ state: { completed: true }, version: 0 }));
      });

      if (PAGES.some((p) => p.auth)) {
        try {
          await login(page);
        } catch (err) {
          console.error(`✗ Login failed for ${themeDef.name}: ${err.message}`);
          await context.close();
          continue;
        }
      }

      await applyTheme(page, themeDef);

      for (const pageDef of PAGES) {
        const enriched = { ...pageDef, themeName: themeDef.name };
        try {
          const result = await capturePage(page, enriched);
          results.push({ ...result, theme: themeDef.name, page: pageDef.name });
          console.log(`✓ ${result.fileName} (errors=${result.consoleErrors}, overflowX=${result.overflowX}px)`);
        } catch (err) {
          console.error(`✗ ${pageDef.name} ${themeDef.name}: ${err.message}`);
          results.push({ fileName: "-", consoleErrors: 0, overflowX: 0, theme: themeDef.name, page: pageDef.name, error: err.message });
        }
        // Conservative throttle to avoid ECS/nginx rate limits.
        await page.waitForTimeout(8000);
      }

      await context.close();
      // Long cooldown between theme sessions.
      if (themeDef !== THEMES[THEMES.length - 1]) {
        await new Promise((r) => setTimeout(r, 20000));
      }
    }
  } finally {
    await browser.close();
  }

  const total = results.length;
  const errors = results.filter((r) => r.consoleErrors > 0).length;
  const overflows = results.filter((r) => r.overflowX > 0).length;
  const failures = results.filter((r) => r.error).length;

  console.log("\n=== Phase 7 ECS Desktop Validation Summary ===");
  console.log(`Base URL: ${BASE_URL}`);
  console.log(`Screenshots: ${total} (${OUT_DIR})`);
  console.log(`Pages with console errors: ${errors}`);
  console.log(`Pages with horizontal overflow: ${overflows}`);
  console.log(`Failed captures: ${failures}`);

  if (overflows > 0) {
    console.log("\nOverflow details:");
    results.filter((r) => r.overflowX > 0).forEach((r) => {
      console.log(`  ${r.page} / ${r.theme}: +${r.overflowX}px`);
    });
  }

  if (failures > 0) {
    process.exitCode = 1;
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
