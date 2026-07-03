#!/usr/bin/env node
/**
 * AD-Research SPA end-to-end smoke test (M24).
 *
 * Why this script exists:
 *   We do not have the dev server or backend running in this sandbox. The
 *   SPA still builds and the build artefacts are in web/dist. We:
 *     1. Serve dist/ over a local HTTP server.
 *     2. Stub every /api/v1/* call with deterministic JSON via Playwright
 *        route() so the React tree mounts and pages render.
 *     3. Pre-seed a fake token + user into localStorage so RequireAuth passes.
 *     4. For each target route, navigate, wait for the route-suspense fallback
 *        to resolve, capture console errors, page errors, and request
 *        failures, then assert that the page produced *some* content.
 *
 * What "rendering" means here:
 *   Since we mock API responses, any runtime exception inside a page
 *   component (e.g. undefined.foo, hook misuse, missing export) shows up
 *   as a pageerror or console error. UI assertions check for sentinel
 *   strings we know exist in each page (K15 DailyLesson, K14 scenario
 *   cards, K11 FRED empty-state copy, K12 category chip, etc.).
 *
 * Usage:
 *   node web/scripts/e2e-smoke.mjs            # full run (writes web/scripts/e2e-report.json)
 *   node web/scripts/e2e-smoke.mjs --keep     # leave the static server running
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..');
const DIST = path.join(ROOT, 'web', 'dist');

// ---------- tiny static server for dist/ ----------

function contentTypeFor(filename) {
  const ext = path.extname(filename).toLowerCase();
  switch (ext) {
    case '.html':
      return 'text/html; charset=utf-8';
    case '.js':
      return 'application/javascript; charset=utf-8';
    case '.mjs':
      return 'application/javascript; charset=utf-8';
    case '.css':
      return 'text/css; charset=utf-8';
    case '.json':
      return 'application/json; charset=utf-8';
    case '.svg':
      return 'image/svg+xml';
    case '.png':
      return 'image/png';
    case '.jpg':
    case '.jpeg':
      return 'image/jpeg';
    case '.gif':
      return 'image/gif';
    case '.webp':
      return 'image/webp';
    case '.ico':
      return 'image/x-icon';
    case '.woff':
    case '.woff2':
      return 'font/woff2';
    case '.ttf':
      return 'font/ttf';
    default:
      return 'application/octet-stream';
  }
}

function createStaticServer(rootDir) {
  return http.createServer((req, res) => {
    try {
      const url = new URL(req.url, 'http://localhost');
      let pathname = decodeURIComponent(url.pathname);
      // SPA fallback: serve index.html for any non-asset path.
      const candidate = path.join(rootDir, pathname);
      const looksLikeAsset =
        pathname.startsWith('/assets/') ||
        pathname === '/favicon.ico' ||
        /\.[a-zA-Z0-9]+$/.test(pathname);
      let servePath = candidate;
      if (!looksLikeAsset || !fs.existsSync(candidate)) {
        servePath = path.join(rootDir, 'index.html');
      }
      const data = fs.readFileSync(servePath);
      res.writeHead(200, {
        'content-type': contentTypeFor(servePath),
        'cache-control': 'no-store',
      });
      res.end(data);
    } catch (err) {
      res.writeHead(500, { 'content-type': 'text/plain' });
      res.end(`static server error: ${err?.message || err}`);
    }
  });
}

// ---------- API stubs ----------
//
// Stub everything under /api/v1 so the SPA never blocks on a real backend.
// The SPA stores auth state in localStorage, so we don't even need /auth/me
// to round-trip — but we do want it to behave realistically so RequireAuth
// resolves and protected pages mount.

function installApiStubs(context) {
  // Build a single router that matches by URL prefix / exact path so we
  // don't depend on Playwright's route() resolution order (which differs
  // across versions and gives surprising precedence to the catch-all).
  const matchers = [];
  // Sentinel object used to mark a matcher as "respond with text/event-stream".
  // We can't rely on `null` because the helper accepts either a plain JSON
  // value *or* a function producing one — the function form was a special case
  // for `/stream/` but it collided with the helper signature.
  const STREAM_SENTINEL = Symbol('stream');
  const on = (pattern, handler) => matchers.push({ pattern, handler });
  const exact = (path, body) => on(`__EXACT__${path}`, () => body);
  const prefix = (path, body) => on(`__PREFIX__${path}`, () => body);

  // ---- auth ----
  exact('/auth/me', {
    id: 1,
    username: 'smoke',
    role: 'admin',
  });
  exact('/auth/login', {
    access_token: 'fake-access',
    refresh_token: 'fake-refresh',
    user: { id: 1, username: 'smoke', role: 'admin' },
  });
  exact('/auth/refresh', { access_token: 'fake-access-2' });

  // ---- dashboard aggregates ----
  //
  // We provide two flavours of empty payloads:
  //   * emptyArray() — for hooks that call .find/.some/.length directly
  //     (PoolList expects a bare array, ScoreRanking templates, Macro
  //     indicators, etc.).
  //   * emptyList() — for paginated endpoints that document { items, total }.
  //
  // Picking the wrong shape only obscures real bugs, so the stubs err on
  // the side of bare arrays unless the API contract is known to wrap them.
  const emptyArray = () => [];
  const emptyList = (extra = {}) => ({ items: [], total: 0, ...extra });

  prefix('/stats/', {
    total_etfs: 0,
    total_pools: 0,
    total_news: 0,
    latest_trade_date: null,
  });
  prefix('/news', emptyList());
  prefix('/macro/indicators', emptyArray());
  prefix('/macro/series', {
    code: '',
    region: '',
    points: [],
    name_zh: '',
    unit: '',
    source: '',
  });
  prefix('/macro/latest', emptyArray());
  prefix('/macro/', { items: [], latest: null, updated_at: null });
  prefix('/scores/templates', emptyArray());
  prefix('/scores', { items: [], total: 0 });
  prefix('/pools', emptyArray());
  prefix('/learn/', {
    learned: [],
    streak: 0,
    week_count: 0,
    total: 0,
  });
  prefix('/favorites/', { favorites: [] });
  prefix('/screen/', emptyList());
  prefix('/instruments', emptyList());
  prefix('/signals/', emptyList());
  prefix('/futures/', emptyList());
  prefix('/research-notes/', emptyList());
  prefix('/strategies/', emptyList());
  prefix('/backtests/', emptyList());
  prefix('/chat/', { answer: '', done: true });
  prefix('/notifications/', emptyList());
  prefix('/sentiment/', { score: 50, label: 'neutral', items: [] });
  prefix('/microstructure/', emptyList());
  prefix('/search-trends/', emptyList());
  prefix('/research-reports/', emptyList());
  prefix('/cninfo-reports/', emptyList());
  prefix('/sec-filings/', emptyList());
  prefix('/listing-events/', emptyList());
  prefix('/crypto/', emptyList());
  prefix('/paper-trading/', emptyList());
  prefix('/trading/', emptyList());
  prefix('/portfolio/', {
    summary: {
      total_market_value: 0,
      total_pnl: 0,
      total_pnl_pct: 0,
      as_of: null,
    },
    holdings: [],
    target_diff: [],
  });
  prefix('/etl/', { tasks: [], runs: [] });
  prefix('/admin/', emptyList());
  prefix('/reports/', emptyList());
  prefix('/market/', emptyList());
  prefix('/scanner/', emptyList());
  prefix('/analysis/', emptyArray());

  // ---- Global Markets (K11 FRED): explicit empty state when API key missing ----
  prefix('/global-markets/', {
    fred_missing: true,
    as_of: null,
    indicators: [],
  });

  // SSE-style endpoints: respond with text/event-stream so EventSource does
  // not log "MIME type application/json" warnings. The body closes immediately.
  prefix('/stream/', STREAM_SENTINEL);

  context.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api\/v1/, '');
    let body = null;
    let isStream = false;
    for (const m of matchers) {
      if (m.pattern.startsWith('__EXACT__')) {
        if (path === m.pattern.slice('__EXACT__'.length)) {
          body = m.handler();
          break;
        }
      } else if (m.pattern.startsWith('__PREFIX__')) {
        const p = m.pattern.slice('__PREFIX__'.length);
        if (path.startsWith(p)) {
          body = m.handler();
          isStream = body === STREAM_SENTINEL;
          break;
        }
      }
    }
    if (isStream) {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream; charset=utf-8',
        body: ': close\n\n',
        headers: { 'cache-control': 'no-store' },
      });
      return;
    }
    if (body === null || body === undefined) {
      body = emptyArray();
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json; charset=utf-8',
      body: JSON.stringify(body),
    });
  });
}

// ---------- Per-route expectations ----------
//
// Each entry: { path, mustContain (sentinel text), allowErrors? }
//
// Sentinels are intentionally chosen from the production page source so they
// stay meaningful if the page is replaced with a stub.

const ROUTES = [
  {
    path: '/login',
    mustContain: ['AD-Research', '登 录'],
    note: 'Login page (no auth required)',
  },
  {
    path: '/dashboard',
    mustContain: ['今日学习', '组合中心', 'dashboard'],
    note: 'K15 DailyLesson + K16 portfolio chip row',
  },
  {
    path: '/learning',
    mustContain: ['估值', '央行', '回测'],
    note: 'K14 — 3 scenario cards (valuation / macro / backtest)',
  },
  {
    path: '/global',
    mustContain: ['FRED', '全球'],
    note: 'K11 FRED empty-state copy when API key missing',
  },
  {
    path: '/news',
    mustContain: ['地缘', '资讯'],
    note: 'K12 event_category chip (geopolitics = 地缘)',
  },
  {
    path: '/instruments',
    mustContain: ['标的', 'instruments'],
    note: 'Instrument list reachable',
  },
  {
    path: '/pools',
    mustContain: ['标的池', 'pools'],
    note: 'Pool list reachable',
  },
  {
    path: '/scores',
    mustContain: ['评分', 'scores'],
    note: 'Score ranking reachable',
  },
  {
    path: '/signals',
    mustContain: ['信号', 'signals'],
    note: 'Signal dashboard reachable',
  },
  {
    path: '/macro',
    mustContain: ['宏观', 'macro'],
    note: 'Macro page reachable',
  },
];

// ---------- main ----------

async function visit(page, baseUrl, route, authed = true) {
  const entry = {
    path: route.path,
    note: route.note,
    console_errors: [],
    console_warnings: [],
    page_errors: [],
    request_failures: [],
    reached: false,
    sentinels_found: {},
    final_url: null,
    note_extra: null,
  };

  const onConsole = (msg) => {
    const type = msg.type();
    const text = msg.text();
    if (type === 'error') entry.console_errors.push(text);
    else if (type === 'warning') entry.console_warnings.push(text);
  };
  const onPageError = (err) => entry.page_errors.push(String(err?.stack || err));
  const onRequestFailed = (req) => {
    const url = req.url();
    if (url.includes('fonts.googleapis.com') || url.includes('fonts.gstatic.com')) return;
    entry.request_failures.push(`${req.failure()?.errorText || 'failed'} ${url}`);
  };
  const onRequest = (req) => {
    const url = req.url();
    if (url.includes('/api/v1/')) {
      entry.request_log = entry.request_log || [];
      if (entry.request_log.length < 25) entry.request_log.push(url);
    }
  };

  page.on('console', onConsole);
  page.on('pageerror', onPageError);
  page.on('requestfailed', onRequestFailed);
  page.on('request', onRequest);

  try {
    // For unauthenticated routes, tell the init script to skip seeding.
    // For authed routes (the default), make sure the flag isn't set.
    await page.goto(`${baseUrl}/_init`, { waitUntil: 'domcontentloaded' });
    if (!authed) {
      await page.evaluate(() => {
        window.localStorage.setItem('__smoke_auth__', 'off');
        try {
          window.localStorage.removeItem('token');
          window.localStorage.removeItem('refresh_token');
          window.localStorage.removeItem('auth-storage');
        } catch (e) {
          /* noop */
        }
      });
    } else {
      await page.evaluate(() => {
        window.localStorage.removeItem('__smoke_auth__');
      });
    }
    await page.goto(`${baseUrl}${route.path}`, {
      waitUntil: 'domcontentloaded',
      timeout: 20_000,
    });
    try {
      await page.waitForFunction(
        () => !document.querySelector('.route-suspense'),
        null,
        { timeout: 10_000 }
      );
    } catch {
      entry.note_extra = 'route-suspense still visible after 10s';
    }
    await page.waitForTimeout(500);

    const text = (await page.evaluate(() => document.body.innerText || '')).trim();
    entry.reached = !!text;
    entry.final_url = page.url();
    for (const s of route.mustContain) {
      entry.sentinels_found[s] = text.includes(s);
    }
    entry.dom_summary = await page.evaluate(() => {
      const root = document.getElementById('root');
      return {
        root_html_length: root?.innerHTML?.length || 0,
        visible_text_length: (document.body.innerText || '').trim().length,
        has_global_error: !!document.querySelector('.global-error-boundary'),
        has_route_suspense: !!document.querySelector('.route-suspense'),
        h1: document.querySelector('h1')?.innerText || null,
        title: document.title,
      };
    });
  } catch (err) {
    entry.note_extra = `goto failed: ${err?.message || err}`;
  } finally {
    page.off('console', onConsole);
    page.off('pageerror', onPageError);
    page.off('requestfailed', onRequestFailed);
    page.off('request', onRequest);
  }
  return entry;
}

async function main() {
  if (!fs.existsSync(path.join(DIST, 'index.html'))) {
    console.error(`dist/index.html not found at ${DIST}. Run "npm run build" first.`);
    process.exit(2);
  }

  const server = createStaticServer(DIST);
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const { port } = server.address();
  const baseUrl = `http://127.0.0.1:${port}`;
  console.log(`[smoke] static server serving dist/ at ${baseUrl}`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    locale: 'zh-CN',
    viewport: { width: 1366, height: 900 },
  });
  installApiStubs(context);

  // Pre-seed auth for protected pages, but allow /login to start unauthenticated
  // by exposing a flag we can flip from inside the page. We do this with a
  // flag on localStorage that the init script checks.
  await context.addInitScript(() => {
    if (window.localStorage.getItem('__smoke_auth__') !== 'off') {
      window.localStorage.setItem('token', 'fake-access');
      window.localStorage.setItem('refresh_token', 'fake-refresh');
      window.localStorage.setItem(
        'auth-storage',
        JSON.stringify({
          state: {
            token: 'fake-access',
            refreshToken: 'fake-refresh',
            user: { id: 1, username: 'smoke', role: 'admin' },
            isAuthenticated: true,
          },
          version: 0,
        })
      );
    }
  });

  const page = await context.newPage();

  const report = {
    started_at: new Date().toISOString(),
    base_url: baseUrl,
    routes: [],
    summary: {},
  };

  for (const route of ROUTES) {
    const authed = route.path !== '/login';
    const entry = await visit(page, baseUrl, route, authed);
    report.routes.push(entry);
    const consoleBadge = entry.console_errors.length
      ? ` [${entry.console_errors.length} console error]`
      : '';
    console.log(
      `[smoke] ${route.path.padEnd(14)} reached=${entry.reached} sentinels=${JSON.stringify(entry.sentinels_found)} pageerrors=${entry.page_errors.length}${consoleBadge}`
    );
  }

  // -------- HelpPopover probe across modes --------
  //
  // HelpPopover reads mode from useSettingsStore. We poke the store through
  // localStorage to switch between 'novice' and 'pro' and visit Dashboard
  // each time, listening for thrown errors. This covers the HelpPopover
  // "高频页面是否能在不同 mode 下不报错" requirement.
  const helpModes = ['novice', 'pro'];
  for (const mode of helpModes) {
    const entry = {
      path: `/dashboard?helpMode=${mode}`,
      note: `HelpPopover probe (mode=${mode})`,
      console_errors: [],
      console_warnings: [],
      page_errors: [],
      request_failures: [],
      reached: false,
      sentinels_found: {},
      final_url: null,
      note_extra: null,
    };
    const onConsole = (msg) => {
      const t = msg.type();
      if (t === 'error') entry.console_errors.push(msg.text());
      else if (t === 'warning') entry.console_warnings.push(msg.text());
    };
    const onPageError = (err) => entry.page_errors.push(String(err?.stack || err));
    const onRequestFailed = (req) => {
      const url = req.url();
      if (url.includes('fonts.googleapis.com') || url.includes('fonts.gstatic.com')) return;
      entry.request_failures.push(`${req.failure()?.errorText || 'failed'} ${url}`);
    };
    page.on('console', onConsole);
    page.on('pageerror', onPageError);
    page.on('requestfailed', onRequestFailed);
    try {
      await page.goto(`${baseUrl}/dashboard`, { waitUntil: 'domcontentloaded' });
      // Switch mode in the persisted settings store.
      await page.evaluate((m) => {
        const raw = window.localStorage.getItem('settings-storage');
        const obj = raw ? JSON.parse(raw) : { state: {}, version: 0 };
        obj.state = { ...(obj.state || {}), mode: m };
        window.localStorage.setItem('settings-storage', JSON.stringify(obj));
      }, mode);
      await page.reload({ waitUntil: 'domcontentloaded' });
      await page
        .waitForFunction(() => !document.querySelector('.route-suspense'), null, { timeout: 10_000 })
        .catch(() => {});
      await page.waitForTimeout(400);
      entry.reached = true;
      entry.final_url = page.url();
      entry.dom_summary = await page.evaluate(() => ({
        root_html_length: document.getElementById('root')?.innerHTML?.length || 0,
        visible_text_length: (document.body.innerText || '').trim().length,
      }));
    } catch (err) {
      entry.note_extra = `helpMode probe failed: ${err?.message || err}`;
    } finally {
      page.off('console', onConsole);
      page.off('pageerror', onPageError);
      page.off('requestfailed', onRequestFailed);
    }
    report.routes.push(entry);
    console.log(
      `[smoke] HelpPopover mode=${mode} pageerrors=${entry.page_errors.length} consoleerrors=${entry.console_errors.length}`
    );
  }

  // -------- summary --------
  report.finished_at = new Date().toISOString();
  const total = report.routes.length;
  const reached = report.routes.filter((r) => r.reached).length;
  const noPageError = report.routes.filter((r) => r.page_errors.length === 0).length;
  const allSentinels = report.routes.filter((r) =>
    Object.values(r.sentinels_found || {}).every(Boolean)
  ).length;
  report.summary = { total, reached, noPageError, allSentinels };

  await browser.close();
  await new Promise((r) => server.close(r));

  const reportPath = path.join(__dirname, 'e2e-report.json');
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(`[smoke] report written to ${reportPath}`);
  console.log(`[smoke] summary:`, report.summary);

  // Exit code: fail if any page produced an unhandled error.
  const fatal = report.routes.some((r) => r.page_errors.length > 0);
  process.exit(fatal ? 1 : 0);
}

main().catch((err) => {
  console.error('[smoke] fatal:', err);
  process.exit(2);
});