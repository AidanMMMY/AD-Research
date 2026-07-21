/* ============================================================
   Chart Color Resolver (dataviz P0-1 / P0-2 / P0-3)

   ECharts and other canvas-based renderers cannot parse CSS
   custom properties like `var(--accent)` — they expect literal
   color strings inside `option` objects. This utility resolves
   CSS variable tokens at chart-init time so colors track the
   active theme when `data-theme` (or `data-accent` /
   `data-color-convention`) on <html> changes.

   API differs from `cssVar.ts`:
     - `token` is the BARE var name (`'--text-tertiary'`),
       not the wrapped `'var(--text-tertiary)'` form.
     - Built-in dark-mode fallbacks mean callers usually
       only pass the token.
     - `subscribeChartThemeCache(fn)` provides a single
       invalidation channel shared across all chart pages.

   Usage:
     const colors = useMemo(() => ({
       accent:    resolveChartColor('--accent'),
       axisLine:  resolveChartColor('--text-tertiary'),
       splitLine: resolveChartColor('--border-default'),
     }), [themeTick]);

     useEffect(
       () => subscribeChartThemeCache(() => setThemeTick(t => t + 1)),
       [],
     );

   Performance: only call at chart-init or inside `useMemo`.
   Each call reads computed style — do NOT invoke inside
   per-frame render loops.
   ============================================================ */

import { readCssVar } from './cssVar';

/**
 * Built-in dark-mode fallbacks. These mirror the dark-theme defaults in
 * `theme.css` so SSR / no-DOM callers still get a sensible value (dark is
 * the default theme since 2026-07-21). In the browser, callers get the
 * actual computed value for the active theme via `readCssVar`.
 */
const DEFAULT_FALLBACKS: Record<string, string> = {
  '--text-primary': '#E6EDF3',
  '--text-secondary': '#A0A0A0',
  '--text-tertiary': '#9CA3AF',
  '--text-muted': '#7B828E',
  '--border-default': '#30363D',
  '--border-strong': '#484F58',
  '--bg-base': '#0D1117',
  '--bg-elevated': '#161B22',
  '--bg-surface': '#1C2128',
  '--accent': '#60A5FA',
  '--accent-dim': 'rgba(96, 165, 250, 0.12)',
  '--color-rise': '#FF8585',
  '--color-fall': '#7DCB99',
  '--color-neutral': '#888888',
};

/**
 * Resolve a CSS custom property token to its computed color value.
 * Pass-through for inputs that are not CSS-var tokens (literal hex,
 * rgb(), etc.).
 */
export function resolveChartColor(token: string, fallback?: string): string {
  if (!token.startsWith('--')) return token;
  const fb = fallback ?? DEFAULT_FALLBACKS[token] ?? '#000000';
  return readCssVar(token, fb);
}

/**
 * Resolve a list of CSS variable tokens. Each token's fallback is
 * looked up by index, falling back to the first fallback, then a
 * generic default.
 */
export function resolveChartColors(tokens: string[], fallbacks: string[]): string[] {
  return tokens.map(
    (t, i) => resolveChartColor(t, fallbacks[i] ?? fallbacks[0] ?? '#000000'),
  );
}

// ------------------------------------------------------------
// Theme-change cache invalidation
//
// All chart pages subscribe to a single `themechange` listener.
// Subscribers typically bump a `themeTick` state so memoised
// chart options re-compute with fresh colors. The listener is
// installed lazily on first subscriber.
// ------------------------------------------------------------

const subscribers = new Set<() => void>();
let installed = false;

function ensureInstalled(): void {
  if (installed || typeof document === 'undefined') return;
  installed = true;
  document.addEventListener('themechange', () => {
    subscribers.forEach((fn) => {
      try {
        fn();
      } catch (err) {
        // Don't let one subscriber break the rest — most chart pages
        // are independent and a buggy subscriber should not freeze
        // the whole dashboard.
        // eslint-disable-next-line no-console
        console.error('[chartColors] themechange subscriber threw:', err);
      }
    });
  });
}

/**
 * Subscribe to chart-color cache invalidation. Fires whenever the
 * document's `themechange` event is dispatched (data-theme /
 * data-accent / data-color-convention toggle). Returns an
 * unsubscribe function — callers should call it on unmount.
 */
export function subscribeChartThemeCache(fn: () => void): () => void {
  ensureInstalled();
  subscribers.add(fn);
  return () => {
    subscribers.delete(fn);
  };
}