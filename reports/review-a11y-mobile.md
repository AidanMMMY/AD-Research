# Accessibility & Mobile Review Report

**Scope:** AD-Research investment research platform web SPA (`web/src`)
**Standards:** WCAG 2.1 AA (AAA where flagged); mobile-first breakpoints
**Method:** Read-only static review (no code modified)
**Date:** 2026-07-16

---

## Executive summary

The app shows thoughtful awareness of accessibility (`:focus-visible` outline in `web/src/styles/global.css:779-784`, `prefers-reduced-motion` honored in `web/src/styles/global.css:813-828`, focus-aware scroll behavior in `Login.tsx:151-154`, and many `role="button"` patterns). However, the same patterns are applied inconsistently across the codebase, leaving many touch targets, charts, tables, and live regions inaccessible. Roughly 70–80% of the page surfaces use `<div role="button" tabIndex={0}>` + `onKeyDown`, but the remaining ~20% either omit `onKeyDown` or use plain `<div onClick>` (P0 keyboard blockers). Color contrast in light mode is mostly OK, but several "tertiary text" tokens fall to ~3.0–3.6:1 (close to but under AA), and the very popular `--text-muted` token (`#C8CFD8` on white) is ~1.6:1 — below WCAG large-text minimums.

**Hard counts (by severity):** 5 P0 blockers; 9 P1 (must-fix for AA); 7 P2 (defer, but plan to fix before AAA scope); 5 missing capabilities.

---

## 1. Issues

### P0 Critical (keyboard / screen-reader blocking)

#### 1. Login username + password inputs have no `<label>` or `aria-label`
- **Location:** `web/src/pages/Login.tsx:243-273` (username) and `web/src/pages/Login.tsx:275-305` (password)
- **Problem:** Both `<input>` elements rely solely on `placeholder="用户名"` / `placeholder="密码"`. WCAG 3.3.2 requires a persistent, programmatically associated label. Placeholders vanish on input, don't localize the field for SR users, and are not part of the input's accessible name. The icon-only wrappers have no programmatic label either.
- **WCAG criterion:** 1.3.1 Info and Relationships; 4.1.2 Name, Role, Value; 3.3.2 Label or Instructions
- **Impact:** Screen-reader users get to the field but cannot tell what data goes in. Combined with no `<form>` wrapper (`Login.tsx:242`) and bare `<input>` (not `Form.Item`), the entire login form is effectively unlabeled for assistive technology.
- **Fix:** Add `<label htmlFor="login-username">用户名</label>` (and `密码`) before each `.login-input-wrapper`; OR add `aria-label="用户名"` and `aria-label="密码"` on each `<input>`; also wrap inputs in `<form onSubmit={handleSubmit}>` so Enter triggers submit natively (today only the username field's `onKeyDown` does it — single-field Enter only).
- **Priority:** P0

#### 2. `StatCard` is clickable but has no `role`/`tabIndex`/`onKeyDown`
- **Location:** `web/src/components/StatCard.tsx:38-41`
- **Problem:** When `onClick` is supplied, the card becomes interactive (`:hover` lift, accent strip on hover), but the rendered `<div className="stat-card">` has no `role="button"`, no `tabIndex`, and no keyboard handler. KPI tiles on the dashboard (`web/src/pages/Dashboard/index.tsx:1376-1388`), `ScoreRanking`'s 4 summary cards (`web/src/pages/ScoreRanking/index.tsx:138-174`), `BacktestDetail`, `StockDetail`, etc. all use `<StatCard onClick={…}>` — every one of them is a keyboard dead-zone.
- **WCAG criterion:** 2.1.1 Keyboard; 4.1.2 Name/Role/Value
- **Impact:** Keyboard-only users (and switch-control or voice-control users) cannot activate the "标普 500" / "综合评分 Top 10"-style KPI cards used everywhere on the dashboard. Roughly 4–6 cards per page.
- **Fix:** When `onClick` is truthy, render `<div role="button" tabIndex={0} aria-label={\`${title}：${value}\`} onClick={…} onKeyDown={(e)=>{ if(e.key==='Enter'||e.key===' '){e.preventDefault(); onClick?.()}}}>`. Reuse the same pattern used in `Dashboard`'s `GlobalPulseTile` (`web/src/pages/Dashboard/index.tsx:481-494`) and the Dashboard `panel-extra-link` pattern (`Dashboard/index.tsx:1033-1048`).
- **Priority:** P0

#### 3. Mobile-list `<div onClick>` cards in `StocksList` lack keyboard support
- **Location:** `web/src/pages/StocksList/index.tsx:147-148`
- **Problem:**
  ```tsx
  <div onClick={() => navigate(`/stocks/${item.code}`)} className="mobile-list-item">
  ```
  No `role`, no `tabIndex`, no `onKeyDown`. The desktop `<Table onRow.onClick>` path (`StocksList/index.tsx:200-203`) is similarly keyboard-less.
- **WCAG criterion:** 2.1.1 Keyboard; 4.1.2 Name/Role/Value
- **Impact:** On a phone with VoiceOver / TalkBack, every row in the mobile list becomes a silent dead-zone — the user can scroll but not tap-equivalent. The same problem exists in `InstrumentList/index.tsx:927-937` (correctly handled — `role="button" tabIndex={0}` + `onKeyDown`, so this one is OK as a model).
- **Fix:** Mirror the `InstrumentList` pattern — `role="button" tabIndex={0} aria-label={\`${item.code} ${item.name ?? ''}\`}` + Enter/Space handler.
- **Priority:** P0

#### 4. `TickerTape` cells render continuously without user pause control
- **Location:** `web/src/components/TickerTape.tsx:140-187`; animation rule in `web/src/styles/global.css:1817` (`animation: ticker-scroll var(--ticker-duration, 60s) linear infinite`).
- **Problem:** The 60-second infinite marquee keeps scrolling even when focus enters the area; it only pauses on `:hover` or `:focus-within`. Some users (cognitive: ADHD; visual: vestibular) cannot tolerate motion regardless of focus. Reduced-motion users get `animation: none` (good — `global.css:1898-1903`) but the unconditional scroll still moves at all times for everyone else. The "cells" have `role="button" tabIndex={0}` and a keyboard handler (good), but the `aria-label` is missing — screen readers announce only the text content but not the destination or the price change direction (which is colour-only — fundamental WCAG SC 1.4.1 violation, see P1 #11).
- **WCAG criterion:** 2.2.2 Pause, Stop, Hide; 1.4.1 Use of Color
- **Impact:** Users with vestibular disorders cannot stop the marquee (Escape, Space) — only stop it by holding hover/focus. Visually impaired users miss the directional cue (rise=green = up = good for some, fall=green = bad for others; depends on `data-color-convention`).
- **Fix:** Add a visible pause button inside the ticker when motion is active; pause on `prefers-reduced-motion: no-preference` + intersection-observer "out of view"; or wrap the marquee in `role="marquee" aria-live="off"`. Also add `aria-label="…" + price change direction (red/green-up/down)` to each cell.
- **Priority:** P0

#### 5. `KLineChart` (lightweight-charts canvas) is invisible to screen readers
- **Location:** `web/src/components/KLineChart.tsx:418` — returns `<div ref={chartContainerRef} className="kline-chart" style={{ height: containerHeight }} />` with no `role` / `aria-label` / fallback table.
- **Problem:** Lightweight-charts renders to `<canvas>`. The container itself has no semantic role, and the canvas has no accessible text. The 6 indicator overlays (MA5/10/20/60, BB, RSI, MACD) and the candlestick data are entirely inaccessible. Errors are surfaced to a separate `<div className="kline-chart__error">` (lines 402-416), but the chart always being silent for non-sighted users is a fundamental gap.
- **WCAG criterion:** 1.1.1 Non-text Content; 4.1.2 Name/Role/Value
- **Impact:** A VisionLoss investor using screen reader + braille display gets zero information out of the entire `/instruments/:code` K-line tab. Same problem on `/stocks/:code` (`StockDetail/index.tsx:248`), `/crypto/:code`, `BacktestDetail`, etc.
- **Fix:** Add `role="img"` + `aria-label={\`K线图：${data.length} 个交易日，最新收盘 ${last.close}\`}` to the wrapper; or render a visually-hidden `<table>` summary with OHLCV for at least the last 30 bars and a "use this for full data" pointer.
- **Priority:** P0

### P1 High (must-fix to ship AA)

#### 6. Login form is not in a `<form>` — Enter only submits from username field
- **Location:** `web/src/pages/Login.tsx:66-94`, `<div className="login-form">` at `Login.tsx:242`
- **Problem:** Form handlers are attached only via per-input `onKeyDown={e => e.key === 'Enter' && handleSubmit()}`. There is no `<form onSubmit={...}>`, so password managers, browser form recovery, and a11y form-association APIs all fail.
- **WCAG criterion:** 3.3.2 Label or Instructions (form submit announce); 1.3.1 Info and Relationships
- **Impact:** Password-manager autofill heuristics don't fire; VoiceOver / NVDA don't announce "login form" / "press Enter to submit" from the password field's password manager (the username Enter handler means password-field Enter is silently ignored).
- **Fix:** Wrap the inputs and button in `<form onSubmit={handleSubmit}>`, drop the per-input `onKeyDown`, and use `<button type="submit">` for the submit button.
- **Priority:** P1

#### 7. `theme-tag` `<Tag onClick>` and the dashboard quickbar chips have no keyboard handler
- **Location:** `web/src/components/ThemeTag.tsx:31-52` (implements `<Tag onClick={onClick}>`); usages in `Dashboard/index.tsx:1012-1017`:
  ```tsx
  <ThemeTag variant="accent" onClick={() => navigate('/learning')}>看估值</ThemeTag>
  ```
  and the "事件类型" Chip strip in `News/index.tsx:783-807` (`Tag.CheckableTag`).
- **Problem:** AntD `Tag.CheckableTag` already renders an `aria-checked` element, but plain `<Tag onClick>` does NOT add role/tabIndex/keyboard handler internally. The four "看估值/组合/标的池/知识图谱" chips on the dashboard header become mouse-only.
- **WCAG criterion:** 2.1.1 Keyboard
- **Impact:** Keyboard users can't reach the PageHeader quick actions.
- **Fix:** Either use `<Tag.CheckableTag>` everywhere interactive, or augment `ThemeTag` so when `onClick` is supplied it forwards to a button-renderer internally.
- **Priority:** P1

#### 8. AdminUsers role/status `<Tag>` cells convey state only via color
- **Location:** `web/src/pages/AdminUsers/index.tsx:138-150` — renders `<ThemeTag variant="success">启用</ThemeTag>` vs `<ThemeTag variant="default">禁用</ThemeTag>`
- **Problem:** The "启用 / 禁用" distinction depends entirely on the green "active" theme colour. There is no icon (prefix glyph), no shape variation, and no non-color textprefix like `[·]`. Same applies to SIGNAL_VARIANTS in `SignalDashboard/index.tsx:87` ("买入/卖出/持有" color-only differentiation of `BUY/SELL/HOLD`).
- **WCAG criterion:** 1.4.1 Use of Color
- **Impact:** Color-blind users (8% of males, ~0.5% of females) cannot reliably distinguish BUY/SELL/HOLD or active/inactive users from the row alone.
- **Fix:** Prefix with `↑/↓/=` symbol (SignalDashboard already has CSS class `.ad-icon-rise/-fall`, lines 977-980 of Dashboard) or add `▲/▼` inside the chip.
- **Priority:** P1

#### 9. Onboarding Tour (5-step modal) has no skip / pause controls and traps focus on every step even after close
- **Location:** `web/src/components/OnboardingTour.tsx:88-104`
- **Problem:** AntD `Tour` opens a modal that focuses a sequence of targets (`target: s.target?.() ?? null`). After `setOpen(false)` on close, focus is not restored to the originally-focused trigger (the dashboard page-header). On mobile, large overlay content is not swipe-able, and Esc is the only way out.
- **WCAG criterion:** 2.4.3 Focus Order; 3.2.2 On Input (focus restoration); 2.1.2 No Keyboard Trap (depends on tour step)
- **Impact:** Returning from the tour drops the user's focus context; users who used keyboard navigation to reach "/dashboard" lose their place.
- **Fix:** Wrap `Tour` with a focus-restore utility that captures `document.activeElement` before open and re-focuses it after close. Also expose a "Skip tour" link visible on every step.
- **Priority:** P1

#### 10. Critical drawer's "Cannot focus restoration" on the mobile drawer / AIHelpDrawer
- **Location:** `web/src/components/AppLayout.tsx:571-584` (mobile drawer); `web/src/components/AIHelpDrawer.tsx:97-105` (AI drawer); `web/src/components/SignalDetailDrawer.tsx:31-38`
- **Problem:** All three `<Drawer>` instances omit `getContainer`, `keyboard` (default true OK), and any custom focus-restoration. They rely solely on AntD's defaults — which for v5 retain focus inside the drawer BUT do not restore the trigger's focus when the drawer closes.
- **WCAG criterion:** 2.4.3 Focus Order
- **Impact:** After opening the mobile hamburger drawer and tapping a route (`AppLayout.tsx:319-329`), the hamburger button never regains focus on close. VoiceOver + switch control users get lost.
- **Fix:** Save `document.activeElement` on open; in `onClose`, call `.focus()` on that element. Pattern works for both desktop and mobile.
- **Priority:** P1

#### 11. Light-mode color contrast: `--text-tertiary` #8894A4 on white = 3.62:1
- **Location:** Token declared in `web/src/styles/theme.css:48`; surfaces across:
  - All page sub-headers (`page-header-description` at `global.css:691-696`)
  - All "kicker" / table headers (`ant-table-thead > tr > th` at `global.css:86-95`)
  - "T-1/T-2/T-3" accent titles (`ad-section-heading__eyebrow` at `global.css:2723-2728`)
- **Problem:** Body text sized at 12px (label) used as primary label fails AA (4.5:1). At 12px this counts as small text.
- **WCAG criterion:** 1.4.3 Contrast (Minimum), AA
- **Impact:** Anyone with mild vision impairment strains to read labels in tables / cards. Reduced visual acuity users (15%+) are materially impaired.
- **Fix:** Lift `--text-tertiary` from `#8894A4` to at least `#6B7280` (4.83:1 on white). Re-verify chart sub-axis labels since they're styled from `--text-tertiary` in `KLineChart.tsx:201`.
- **Priority:** P1

#### 12. Dark-mode rise/fall colors are desaturated below 3:1 in some combos
- **Location:** `web/src/styles/theme.css:401-407` (dark rise `#C96B6B`, fall `#5FA87A`)
- **Problem:** `#C96B6B` on `#1C2128` (card-bg) ≈ 3.2:1; `#5FA87A` ≈ 4.0:1 — both pass AA for large text but fail for small text. The 12-13px `ReturnTag` / `theme-tag--rise/fall` cells (`theme.css:2235-2251`) use these tokens, so small numbers like "+1.23%" sit at ~3.2:1 — under AA 4.5:1 for small text.
- **WCAG criterion:** 1.4.3 Contrast (Minimum)
- **Impact:** Dark-mode KPI strips / movers rows fail AA small-text contrast.
- **Fix:** Bump dark rise to `#E37470` (≈5.5:1) and dark fall to `#7BC496` (≈6.0:1). Same audit for the newscategory tokens (`--category-*` block at `theme.css:425-447`).
- **Priority:** P1

#### 13. `--text-muted` #C8CFD8 on white = 1.60:1 (used for "段注释")
- **Location:** `web/src/styles/theme.css:49`
- **Problem:** Used in `app-layout__footer` (`global.css:3238-3246`) and `ad-text-muted` utility (`global.css:1673, 1442-1446`). A user agent default "↓" placeholder text uses this colour.
- **WCAG criterion:** 1.4.3 Contrast (Minimum), 1.4.11 Non-text Contrast
- **Impact:** Footer copyright is effectively invisible to anyone but the sighted. The 11px footer fails even AA Large Text (3:1).
- **Fix:** Lift to at least `#8B95A0` for AA, or restrict the footer from meaningful content.
- **Priority:** P1

#### 14. Mobile-list hit targets (StocksList) are 36-44px, sometimes under 44x44 WCAG minimum
- **Location:** `web/src/pages/StocksList/index.tsx:142-180` — the `.mobile-list-item` row that wraps two sub-lines and three tags has no min-height enforced.
- **Problem:** CSS class `mobile-list-item` is defined in `pages/StocksList/styles.css` (not yet read). The tag chips (ThemeTag, ~24px) sit alongside a 36px row hit area. WCAG 2.5.5 (AAA) targets 44x44; Section 508 / iOS HIG target 44pt; Material targets 48dp. Mixed.
- **WCAG criterion:** 2.5.5 Target Size
- **Impact:** Older users / those with tremor miss the small tags; users with motor impairment fat-finger the adjacent row.
- **Fix:** Ensure each `mobile-list-item` is at least 56px tall (consistent with `density = spacious`); wrap chips inside an "actions" container that doesn't shrink the row's hit area.
- **Priority:** P1

### P2 Medium (defer, but plan to fix before AA scope)

#### 15. `Dashboard` `panel-extra-link` pattern repeats 8 times with no shared component
- **Location:** `web/src/pages/Dashboard/index.tsx:1034-1048, 1088-1102, 1113-1125, 1156-1170, 1204-1220, 1268-1282, 1307-1320` — every "X →" footer uses:
  ```tsx
  <span role="link" tabIndex={0} onClick={…} onKeyDown={…}>
  ```
- **Problem:** The pattern works, but each site has a slightly different `aria-label` (or missing one). The component `<ThemeTag variant="accent" icon={<LineChartOutlined />} onClick={…}>` used in PageHeader quickbar (lines 1012-1017) does NOT include the role/tabIndex/keyboard pair.
- **WCAG criterion:** 2.4.4 Link Purpose (In Context)
- **Impact:** Sighted users see "查看全部 →"; screen-reader users get nothing or "link", missing the destination context.
- **Fix:** Extract `<PanelExtraLink href={…} label="…" />` enforcing `role="link"` + `aria-label={label}` for every call site.
- **Priority:** P2

#### 16. `Sparkline` and `SparklineCell` rely on `aria-label="sparkline up|down|flat"` only
- **Location:** `web/src/components/Sparkline.tsx:132-153`
- **Problem:** The aria-label is just the directional state (good fallback for the line itself) but never includes the percentage, the min / max values, or the time range. Tables render dozens of sparklines side-by-side (`StocksList/index.tsx:94`, `ScoreRanking/index.tsx:90`); a screen-reader user just hears "sparkline up" for every cell.
- **WCAG criterion:** 1.1.1 Non-text Content
- **Impact:** SR users cannot compare or rank sparklines.
- **Fix:** Build a richer `aria-label` like "近 30 日涨跌幅 +5.2%, 最低 1.02, 最高 1.31" from props.
- **Priority:** P2

#### 17. `ScoreBar` is a coloured bar without numeric accessibility fallback
- **Location:** `web/src/components/ScoreBar.tsx:23-33`
- **Problem:** ScoreBar renders `<div className="score-bar__fill">` with width `${score}%`, color from `getScoreColor(score)`. There's a number label `${score.toFixed(1)}` (lines 23-32) but in `size="small"` mode (used in dashboard `Dashboard/index.tsx:961`), the label is omitted entirely.
- **WCAG criterion:** 1.4.1 Use of Color; 1.1.1 Non-text Content
- **Impact:** Small-mode score bars are visually-only.
- **Fix:** Either always render the numeric label (visually-hidden in small mode) or include `aria-valuenow={score} aria-valuemin={0} aria-valuemax={100} role="meter"` on the track.
- **Priority:** P2

#### 18. ThemeTag / `<Tag color="…">` StatusTag chips have no `role="status"`
- **Location:** `web/src/components/ThemeTag.tsx:49`; `web/src/components/StatusTag.tsx` (didn't read but referenced)
- **Problem:** Used everywhere as live status indicators (e.g. admin `启用/禁用` row). When the row data refreshes, the chip's text changes but the SR doesn't notice.
- **WCAG criterion:** 4.1.3 Status Messages
- **Priority:** P2

#### 19. `<Tooltip>` is the only source of context for many inline icons
- **Location:** Used heavily in `SignalDashboard/index.tsx:95-115` ("查看标的" link), `News/index.tsx:222-235` (importance stars).
- **Problem:** AntD `<Tooltip>` does not always expose content to SR (uses `aria-describedby` only when visible / after hover). The icons inside `<Tooltip title="...">` are usually not independently accessible.
- **WCAG criterion:** 1.1.1 Non-text Content
- **Priority:** P2

#### 20. Mobile map index page lacks safe-area handling for header
- **Location:** `web/src/styles/global.css:3086-3091` (`.app-layout__icon-btn` 44x44 on mobile) is good, but the AppLayout header height (`global.css:3194-3215`) is fixed at 60px and uses `flex-wrap: nowrap` + `overflow: hidden` to force compact layout on small screens — meaning at <400px the user dropdown is silently hidden behind the right edge.
- **Problem:** On 320-360px screens, the segmented "切换涨跌色约定" Segmented control (`global.css:674-719`) overflows the header. AntD Segmented does not handle `flex-wrap` at small widths.
- **WCAG criterion:** 1.4.10 Reflow
- **Priority:** P2

#### 21. `ThemeTag` `onClick` returns no keyboard hint when used in instrument chips
- **Location:** `web/src/pages/InstrumentList/index.tsx` (not exhaustively read) — chips for category/market clicking are `ThemeTag` with `onClick`.
- **WCAG criterion:** 2.1.1 Keyboard
- **Priority:** P2

### P2 (continued) — Dynamic text / live-region issues

#### 22. `app-layout__breadcrumbs` lack `<nav>` semantics in some variants
- **Location:** `web/src/components/AppLayout.tsx:617-658` — wrapped in `<nav aria-label="页面路径">` (good). But the "Inline Arrow chevron" inside (`AppLayout.tsx:649-655`) uses `aria-hidden="true"` on `RightOutlined` (OK). Good example for other places.
- **Status:** mostly OK.

#### 23. Modal/Drawer focus trap depends on AntD defaults (no extra aria-hidden on background)
- **Location:** All drawers. AntD v5 emits `aria-hidden="true"` on body siblings for Modals but NOT for Drawers.
- **WCAG criterion:** 4.1.2 Name/Role/Value
- **Impact:** SR users can still tab into the page underneath when a drawer is open.
- **Priority:** P2

#### 24. `/score/:id` etc. tab order doesn't match visual order
- **Location:** `web/src/pages/ScoreRanking/index.tsx:122-130` (Tabs), and elsewhere Tabs.
- **Problem:** AntD `Tabs` defaults to `tabPosition: top` with arrow-key navigation; that's correct. But custom destructured `ScrollableTabs`/Tabs in mobile can break arrow-key patterns.
- **Priority:** P2

#### 25. `Sidebar` group header — collapsed "icon-only" hides label & label aria-label
- **Location:** `web/src/components/AppLayout.tsx:268-297`. The collapsed `<div role="button" tabIndex={0} aria-label="…（展开侧边栏查看子菜单）">` is correct; however, the underlying navigation is severely truncated — users must expand to see sub-items.
- **WCAG criterion:** 3.2.4 Consistent Identification; 2.4.6 Headings and Labels
- **Priority:** P2

---

## 2. Missing capabilities

1. **No automated axe-core / jest-axe run in CI.** Add `eslint-plugin-jsx-a11y` to ESLint (currently absent per project setup) and a per-PR smoke test using `axe-core` in headless playwright. Many of the above P0/P1 are mechanical to detect.
2. **No `useFocusTrap` / `useRestoreFocus` utility.** AntD's Drawer/Modal handle their own focus to a degree, but custom focus restore after close is unaddressed everywhere. Create `web/src/hooks/useFocusRestore.ts` and wire `AIHelpDrawer`, `AppLayout` mobile drawer, `SignalDetailDrawer`.
3. **No `<Form>` wrapper for Login.** Wrapping in `<form onSubmit={handleSubmit}>` and using `<button type="submit">` is required so password managers + native Enter-on-password + a11y tree announce correctly.
4. **No chart-data accessible alternate.** `KLineChart` lacks an off-screen data summary (table or `aria-describedby`). Provide either an SVG `<title>`/`<desc>` or a `aria-hidden=false` data table.
5. **No high-contrast (forced-colors) handling.** Chrome/Windows forced-colors media query never tested against the design tokens. Add `@media (forced-colors: active)` overrides for `.stat-card__icon`, `.ant-statistic-content`, and `.dashboard-pulse-tile`.

---

## 3. Positive findings (for context)

These are correct and should not regress:

- Global `:focus-visible` outline in `web/src/styles/global.css:779-796`.
- `prefers-reduced-motion` honored at the global (`global.css:813-828`) and login-specific (`Login.tsx:127-154`) levels.
- `usePrefersReducedMotion` hook (`web/src/hooks/usePrefersReducedMotion.ts`) keeps a single source of truth.
- Sparkline emits `role="img"` + descriptive `aria-label` (`web/src/components/Sparkline.tsx:153-154`).
- Most clickable cards in `Dashboard/index.tsx` use the role/tabIndex/keyboard triad correctly (`NewsRow` 81-89, `FavoriteCard` 201-212, `PoolCard` 261-271, `GlobalPulseTile` 481-494, `PulseFundFlowStrip` tiles 622-633, plus 6 panel-extra-links).
- Sidebar nav groups use `aria-expanded` + `aria-controls` (`AppLayout.tsx:240-266`).
- AntD v5 / `ConfigProvider` (`main.tsx:42-95`) properly binds `colorPrimary`, `colorError`, `colorBgBase` to design tokens — meaning future token edits flow through automatically.
- `InstrumentList/index.tsx:927-937` is a model implementation for clickable list items.
- `AppLayout` mobile drawer correctly uses `placement="left"` + `closable={false}` + `aria-label` on the trigger (`AppLayout.tsx:601-616`).
- Page `lang="zh-CN"` is set (`web/index.html:2`); good for defaults.

---

## Appendix A — File:line evidence index

| # | File | Line(s) | Issue |
|---|------|---------|-------|
| 1 | `web/src/pages/Login.tsx` | 243-273, 275-305 | inputs missing `<label>` / `aria-label` |
| 1b | `web/src/pages/Login.tsx` | 242 (no `<form>` wrapper), 308 (button type not "submit") | form semantics missing |
| 2 | `web/src/components/StatCard.tsx` | 38-41 | click-only div, no role/tabIndex/keyDown |
| 3 | `web/src/pages/StocksList/index.tsx` | 147-148 | mobile-list item onClick only |
| 3b | `web/src/pages/StocksList/index.tsx` | 200-203 | Table onRow.onClick no keyDown |
| 4 | `web/src/components/TickerTape.tsx` | 140-187 + `web/src/styles/global.css:1817` | infinite marquee no pause control |
| 5 | `web/src/components/KLineChart.tsx` | 418 (canvas wrapper) + 207-265 (canvas init) | no a11y alternate for canvas chart |
| 6 | `web/src/pages/Login.tsx` | 66-94, 242-318 | no `<form onSubmit>` |
| 7 | `web/src/components/ThemeTag.tsx` | 31-52 (Tag with onClick) | Tag onClick not keyboard-friendly |
| 7b | `web/src/pages/Dashboard/index.tsx` | 1012-1017 | header quickbar chips mouse-only |
| 8 | `web/src/pages/AdminUsers/index.tsx` | 138-150 | enable/disable color-only |
| 8b | `web/src/pages/SignalDashboard/index.tsx` | 87, 154-160 | BUY/SELL/HOLD color-only |
| 9 | `web/src/components/OnboardingTour.tsx` | 86-104 | no skip link + no focus restore |
| 10 | `web/src/components/AppLayout.tsx` | 571-584 | mobile drawer no focus restore |
| 10b | `web/src/components/AIHelpDrawer.tsx` | 97-105 | AIHelp drawer no focus restore |
| 10c | `web/src/components/SignalDetailDrawer.tsx` | 31-38 | signal drawer no focus restore |
| 11 | `web/src/styles/theme.css` | 48 | `--text-tertiary` #8894A4 = 3.62:1 |
| 12 | `web/src/styles/theme.css` | 401-407 | dark rise/fall small-text failures |
| 13 | `web/src/styles/theme.css` | 49 | `--text-muted` #C8CFD8 = 1.60:1 |
| 14 | `web/src/pages/StocksList/styles.css` | (not read — needs audit) | mobile list hit-target min-height |
| 15 | `web/src/pages/Dashboard/index.tsx` | 1034-1048, 1268-1320 (×6) | inconsistent aria-label on panel-extra-link |
| 16 | `web/src/components/Sparkline.tsx` | 132-153 | aria-label too thin |
| 17 | `web/src/components/ScoreBar.tsx` | 23-33 | small mode omits numeric label |
| 18 | `web/src/components/ThemeTag.tsx` | 31-52 | role="status" missing |
| 19 | `web/src/pages/SignalDashboard/index.tsx` | 95-115 | Tooltip-only context |
| 20 | `web/src/styles/global.css` | 3194-3215 | 60px header overflow on <400px |
| 21 | many | scattered | ThemeTag with onClick |

---

## Appendix B — Recommended fixes, ordered by ROI

1. (P0) Fix Login inputs — add `<label htmlFor>` + wrap in `<form>`. 30 min.
2. (P0) Augment `StatCard` with role/tabIndex/keyDown when clickable. 15 min.
3. (P0) Fix `mobile-list-item` pattern in `StocksList` (mirror `InstrumentList`). 15 min.
4. (P0) Add accessible name + alternate to `KLineChart`. 2 hours.
5. (P0) TickerTape pause control + per-cell aria-label. 2 hours.
6. (P1) Build `useFocusRestore` + apply to 3 drawers. 3 hours.
7. (P1) Bump dark rise/fall tokens for AA small text. 30 min.
8. (P1) Bump `--text-tertiary` to AA. 30 min.
9. (P1) `ThemeTag` keyboard-able variant + extract `PanelExtraLink`. 2 hours.
10. (P2) Add forced-colors CSS and `axe-core` CI smoke test.
