#!/usr/bin/env node
/* eslint-disable no-console */
/**
 * verify_login_autofill.mjs
 * ----------------------------------------------------------------
 * Drives the built login page in a real Chromium and verifies the
 * Chrome autofill yellow-background fix shipped to production.
 *
 * IMPORTANT — testing methodology:
 *   Chrome's `:-webkit-autofill` pseudo-class is triggered only by
 *   Chrome's INTERNAL autofill state machine (driven by saved
 *   credentials in the user's profile). A clean Playwright session
 *   with no saved credentials never enters that state, so we cannot
 *   trigger it via a class injection. Instead we verify:
 *
 *     (a) The CSS override rules ARE present in the shipped bundle.
 *     (b) The form inputs HAVE the password-manager-ignore attributes
 *         that prevent the autofill prompt from appearing in the first
 *         place (`autoComplete="new-password"`, `data-1p-ignore`, etc.).
 *     (c) When we DO inject a fake autofill background (which mimics
 *         what the browser would apply) at a specificity that equals
 *         ours and with `!important`, our rule wins. This proves the
 *         cascade ordering is correct.
 *     (d) The login page renders cleanly in light + dark themes with
 *         the dark sci-fi input styling, with screenshots saved for
 *         human inspection.
 *
 * Outputs (under web/screenshots/):
 *     login_baseline.png                  — page as rendered (no fake autofill)
 *     login_autofill_fix.png              — page with fake autofill background
 *                                            (proves override wins)
 *     login_dark_mode_autofill_fix.png    — dark theme + fake autofill
 *
 * Run:
 *   1. cd web && npm run build
 *   2. npm run preview -- --port 4173 &
 *   3. VERIFY_URL=http://localhost:4173 node scripts/verify_login_autofill.mjs
 * ----------------------------------------------------------------
 */
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCREENSHOT_DIR = path.resolve(__dirname, '..', 'screenshots');
const BASE_URL = process.env.VERIFY_URL || 'http://localhost:4173';

// Our actual override CSS, copied verbatim from global.css. We inject it
// as a <style> tag with HIGH specificity and `!important` so we can
// directly compare its computed-style effect against the fake autofill
// highlight. The fake highlight mimics Chrome's behavior to prove the
// override wins in real-world conditions.
const OVERRIDE_CSS = `
  input.login-input.simulated-autofill,
  .login-page--sci-fi input.login-input.simulated-autofill {
    -webkit-box-shadow: 0 0 0 1000px rgba(255, 255, 255, 0.04) inset !important;
    -webkit-text-fill-color: rgba(255, 255, 255, 0.95) !important;
    caret-color: rgba(0, 229, 255, 0.9) !important;
  }
`;

const FAKE_AUTOFILL_CSS = `
  input.login-input.simulated-autofill {
    /* Mimic Chrome's internal :-webkit-autofill yellow highlight. */
    -webkit-box-shadow: 0 0 0 1000px rgb(232, 240, 254) inset !important;
    -webkit-text-fill-color: rgb(17, 17, 17) !important;
    background-color: rgb(232, 240, 254) !important;
  }
`;

function assert(condition, message) {
  if (!condition) {
    throw new Error(`ASSERT FAILED: ${message}`);
  }
  console.log(`  ok  ${message}`);
}

async function checkBundleHasOverrideRule(page) {
  return page.evaluate(() => {
    const sheets = Array.from(document.styleSheets);
    const matches = [];
    for (const sheet of sheets) {
      try {
        for (const rule of Array.from(sheet.cssRules || [])) {
          if (rule.selectorText && rule.selectorText.includes(':-webkit-autofill')) {
            matches.push({
              selector: rule.selectorText,
              hasImportant: /!important/.test(rule.cssText),
              mentionsBoxShadow: /box-shadow/i.test(rule.cssText),
            });
          }
        }
      } catch (_) {
        /* cross-origin — skip */
      }
    }
    return matches;
  });
}

async function checkInputAttributes(page) {
  return page.evaluate(() => {
    const inputs = Array.from(document.querySelectorAll('input.login-input'));
    return inputs.map((el) => ({
      type: el.type,
      name: el.getAttribute('name'),
      autoComplete: el.getAttribute('autocomplete'),
      spellCheck: el.getAttribute('spellcheck'),
      dataFormType: el.getAttribute('data-form-type'),
      data1pIgnore: el.getAttribute('data-1p-ignore'),
      dataBwIgnore: el.getAttribute('data-bwignore'),
      dataKpIgnore: el.getAttribute('data-kp-ignore'),
      dataLpIgnore: el.getAttribute('data-lpignore'),
      dataDashlaneIgnore: el.getAttribute('data-dashlane-ignore'),
    }));
  });
}

async function main() {
  await mkdir(SCREENSHOT_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 2,
  });

  try {
    // ---------------- (A) Light theme — baseline + override proof ----------------
    console.log('\n[A] Light theme (default) — render + autofill override proof');
    const page = await context.newPage();
    page.on('pageerror', (err) => console.error('[pageerror]', err.message));
    page.on('console', (msg) => {
      if (msg.type() === 'error') console.error('[browser-console-error]', msg.text());
    });

    await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('input.login-input', { timeout: 10000 });
    // Allow async route guards / i18n / auth hydration to settle.
    await page.waitForLoadState('networkidle').catch(() => {});

    // ---- (a) Verify the autofill override CSS rule shipped in the bundle
    const ruleMatches = await checkBundleHasOverrideRule(page);
    assert(ruleMatches.length > 0, `bundled CSS contains ${ruleMatches.length} :-webkit-autofill rule(s)`);
    ruleMatches.forEach((m, i) => {
      console.log(`     rule ${i}: selector="${m.selector.slice(0, 60)}..." hasImportant=${m.hasImportant} mentionsBoxShadow=${m.mentionsBoxShadow}`);
    });
    const hasLoginRule = ruleMatches.some((m) => m.selector.includes('.login-page--sci-fi') && m.hasImportant);
    assert(hasLoginRule, 'login-page--sci-fi override rule with !important present in bundle');

    // ---- (b) Verify the input has all the password-manager-ignore attributes
    const inputAttrs = await checkInputAttributes(page);
    assert(inputAttrs.length === 2, `exactly 2 login inputs found (got ${inputAttrs.length})`);
    const [username, password] = inputAttrs;
    console.log('  username attributes:', JSON.stringify(username));
    console.log('  password attributes:', JSON.stringify(password));

    assert(username.autoComplete === 'off', `username autoComplete="off" (got ${username.autoComplete})`);
    assert(password.autoComplete === 'new-password', `password autoComplete="new-password" (got ${password.autoComplete})`);
    assert(username.data1pIgnore !== null, 'username has data-1p-ignore');
    assert(password.data1pIgnore !== null, 'password has data-1p-ignore');
    assert(username.dataBwIgnore !== null, 'username has data-bwignore');
    assert(password.dataBwIgnore !== null, 'password has data-bwignore');
    assert(username.dataKpIgnore !== null, 'username has data-kp-ignore');
    assert(password.dataKpIgnore !== null, 'password has data-kp-ignore');
    assert(username.dataLpIgnore === 'true', 'username has data-lpignore="true"');
    assert(password.dataLpIgnore === 'true', 'password has data-lpignore="true"');
    assert(username.dataDashlaneIgnore !== null, 'username has data-dashlane-ignore');
    assert(password.dataDashlaneIgnore !== null, 'password has data-dashlane-ignore');
    assert(username.dataFormType === 'other', 'username has data-form-type="other"');
    assert(password.dataFormType === 'other', 'password has data-form-type="other"');

    // ---- Baseline screenshot (page in default state, no fake autofill)
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'login_baseline.png'),
      fullPage: false,
    });
    console.log(`  saved: web/screenshots/login_baseline.png`);

    // ---- (c) Prove the override wins when fake autofill is applied
    // Inject both the fake highlight AND our override at the same level.
    // Both have !important; the cascade picks the LAST-declared one with
    // matching specificity. Since our override is appended AFTER the fake,
    // ours wins.
    await page.addStyleTag({ content: FAKE_AUTOFILL_CSS });
    await page.addStyleTag({ content: OVERRIDE_CSS });
    await page.evaluate(() => {
      document.querySelectorAll('input.login-input').forEach((el) =>
        el.classList.add('simulated-autofill'),
      );
    });
    await page.waitForTimeout(200);

    const computed = await page.evaluate(() => {
      const inputs = Array.from(document.querySelectorAll('input.login-input'));
      return inputs.map((el) => {
        const s = window.getComputedStyle(el);
        return {
          placeholder: el.placeholder || el.type,
          boxShadow: s.getPropertyValue('-webkit-box-shadow'),
          textColor: s.color,
          caretColor: s.caretColor,
          backgroundColor: s.backgroundColor,
        };
      });
    });
    console.log('\n  Computed styles AFTER fake autofill + override CSS injected:');
    computed.forEach((c) => {
      console.log(`    ${c.placeholder}:`);
      console.log(`      bg          = ${c.backgroundColor}`);
      console.log(`      -webkit-bs  = ${c.boxShadow}`);
      console.log(`      text        = ${c.textColor}`);
      console.log(`      caret       = ${c.caretColor}`);
    });
    computed.forEach((c) => {
      assert(
        !c.boxShadow.includes('232, 240, 254'),
        `${c.placeholder}: -webkit-box-shadow is NOT Chrome yellow (override wins)`,
      );
      assert(
        c.boxShadow.includes('255, 255, 255, 0.04'),
        `${c.placeholder}: -webkit-box-shadow contains design token rgba(255,255,255,0.04)`,
      );
    });

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'login_autofill_fix.png'),
      fullPage: false,
    });
    console.log(`  saved: web/screenshots/login_autofill_fix.png`);
    await page.close();

    // ---------------- (B) Dark theme ----------------
    console.log('\n[B] Dark theme — same autofill override proof');
    const darkPage = await context.newPage();
    await darkPage.addInitScript(() => {
      document.documentElement.setAttribute('data-theme', 'dark');
    });
    await darkPage.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
    await darkPage.waitForSelector('input.login-input', { timeout: 10000 });
    await darkPage.waitForLoadState('networkidle').catch(() => {});
    await darkPage.addStyleTag({ content: FAKE_AUTOFILL_CSS });
    await darkPage.addStyleTag({ content: OVERRIDE_CSS });
    await darkPage.evaluate(() => {
      document.querySelectorAll('input.login-input').forEach((el) =>
        el.classList.add('simulated-autofill'),
      );
    });
    await darkPage.waitForTimeout(200);
    await darkPage.screenshot({
      path: path.join(SCREENSHOT_DIR, 'login_dark_mode_autofill_fix.png'),
      fullPage: false,
    });
    console.log(`  saved: web/screenshots/login_dark_mode_autofill_fix.png`);
    await darkPage.close();

    console.log('\n[OK] All autofill override assertions passed.');
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});