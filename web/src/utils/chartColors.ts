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
     - Built-in light-mode fallbacks mean callers usually
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
 * Built-in light-mode fallbacks. These mirror the defaults in
 * `theme.css` so SSR / no-DOM callers still get a sensible
 * value. Dark-theme callers get the actual computed value
 * via `readCssVar`.
 */
const DEFAULT_FALLBACKS: Record<string, string> = {
  '--text-primary': '#0F1115',
  '--text-secondary': '#5B6778',
  '--text-tertiary': '#8894A4',
  '--text-muted': '#C8CFD8',
  '--border-default': '#e5e7eb',
  '--border-strong': '#d1d5db',
  '--bg-base': '#FAFBFC',
  '--bg-elevated': '#F3F5F7',
  '--bg-surface': '#EDF0F3',
  '--accent': '#2563EB',
  '--accent-dim': 'rgba(37, 99, 235, 0.08)',
  '--color-rise': '#C0392B',
  '--color-fall': '#1B7A3C',
  '--color-neutral': '#9ca3af',
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