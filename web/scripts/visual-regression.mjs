#!/usr/bin/env node
/**
 * Phase 7 browser validation script (local backend + Vite dev server).
 *
 * Prerequisites:
 *   docker compose -f docker-compose.local-db.yml up -d
 *   poetry run alembic upgrade head
 *   poetry run python scripts/create_admin_local.py
 *   poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000
 *
 * Then:
 *   cd web && node scripts/visual-regression.mjs
 *
 * The script starts the Vite dev server (port 5173) which proxies /api
 * to the backend (port 8000), logs in as admin, and screenshots key pages.
 */
import { spawn } from "node:child_process";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const FRONTEND_URL = process.env.FRONTEND_URL || "http://localhost:5173";
const ADMIN_USER = process.env.ADMIN_USER || "admin";
const ADMIN_PASS = process.env.ADMIN_PASS || "kWZK*Ee*%sMZ3r-5";
const OUT_DIR = path.resolve(process.cwd(), "screenshots", "phase7");

const VIEWPORTS = [
  { name: "desktop", width: 1280, height: 800 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "mobile", width: 375, height: 812 },
];

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

async function startViteDevServer() {
  console.log("Starting Vite dev server...");
  const child = spawn("npm", ["run", "dev"], {
    cwd: process.cwd(),
    stdio: "pipe",
    shell: true,
  });
  child.stdout.on("data", (d) => process.stdout.write(d));
  child.stderr.on("data", (d) => process.stderr.write(d));
  await waitForServer(FRONTEND_URL);
  console.log("Vite dev server ready.");
  return child;
}

async function login(page) {
  await page.goto(`${FRONTEND_URL}/login`, { waitUntil: "load" });
  await page.fill('input[placeholder="用户名"]', ADMIN_USER);
  await page.fill('input[placeholder="密码"]', ADMIN_PASS);
  // Login button text is "登 录" (with a space) in Login.tsx.
  await page.click('.login-submit');
  await page.waitForURL(/\/(dashboard|instruments)/, { timeout: 15_000 });
}

async function applyTheme(page, themeDef) {
  await page.evaluate(
    ({ theme, convention }) => {
      localStorage.setItem("ad-research-theme", theme);
      localStorage.setItem("ad-research-color-convention", convention);
      // Skip onboarding tour so screenshots are not obscured.
      localStorage.setItem("ad-research-onboarding-storage", JSON.stringify({ state: { completed: true }, version: 0 }));
    },
    { theme: themeDef.theme, convention: themeDef.convention }
  );
  await page.reload({ waitUntil: "load" });
  await page.waitForTimeout(1200);
}

async function capturePage(page, pageDef, themeDef, viewport) {
  const consoleErrors = [];
  const handler = (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(msg.text());
    }
  };
  page.on("console", handler);

  await page.goto(`${FRONTEND_URL}${pageDef.path}`, { waitUntil: "load" });
  // Wait for async data/empty states + skeletons.
  await page.waitForTimeout(1800);

  const fileName = `${pageDef.name}__${themeDef.name}__${viewport.name}.png`;
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
  await waitForServer(`${BACKEND_URL}/health`);
  console.log(`Backend ready at ${BACKEND_URL}`);

  const viteServer = await startViteDevServer();
  const browser = await chromium.launch({ headless: true });
  const results = [];

  try {
    for (const viewport of VIEWPORTS) {
      for (const themeDef of THEMES) {
        const context = await browser.newContext({
          viewport: { width: viewport.width, height: viewport.height },
          deviceScaleFactor: 1,
        });
        const page = await context.newPage();

        // Set theme before login so it applies from first paint.
        await page.goto(`${FRONTEND_URL}/login`, { waitUntil: "load" });
        await page.evaluate(() => {
          localStorage.setItem("ad-research-onboarding-storage", JSON.stringify({ state: { completed: true }, version: 0 }));
        });
        await applyTheme(page, themeDef);

        if (PAGES.some((p) => p.auth)) {
          try {
            await login(page);
            await applyTheme(page, themeDef);
          } catch (err) {
            console.error(`✗ Login failed for ${themeDef.name}: ${err.message}`);
            await context.close();
            continue;
          }
        }

        for (const pageDef of PAGES) {
          try {
            const result = await capturePage(page, pageDef, themeDef, viewport);
            results.push({ ...result, viewport: viewport.name, theme: themeDef.name, page: pageDef.name });
            console.log(`✓ ${result.fileName} (errors=${result.consoleErrors}, overflowX=${result.overflowX}px)`);
          } catch (err) {
            console.error(`✗ ${pageDef.name} ${themeDef.name} ${viewport.name}: ${err.message}`);
            results.push({ fileName: "-", consoleErrors: 0, overflowX: 0, viewport: viewport.name, theme: themeDef.name, page: pageDef.name, error: err.message });
          }
        }

        await context.close();
      }
    }
  } finally {
    await browser.close();
    viteServer.kill("SIGTERM");
  }

  // Summary
  const total = results.length;
  const errors = results.filter((r) => r.consoleErrors > 0).length;
  const overflows = results.filter((r) => r.overflowX > 0).length;
  const failures = results.filter((r) => r.error).length;

  console.log("\n=== Phase 7 Browser Validation Summary ===");
  console.log(`Backend: ${BACKEND_URL}`);
  console.log(`Frontend: ${FRONTEND_URL}`);
  console.log(`Screenshots: ${total} (${OUT_DIR})`);
  console.log(`Pages with console errors: ${errors}`);
  console.log(`Pages with horizontal overflow: ${overflows}`);
  console.log(`Failed captures: ${failures}`);

  if (overflows > 0) {
    console.log("\nOverflow details:");
    results.filter((r) => r.overflowX > 0).forEach((r) => {
      console.log(`  ${r.page} / ${r.theme} / ${r.viewport}: +${r.overflowX}px`);
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
