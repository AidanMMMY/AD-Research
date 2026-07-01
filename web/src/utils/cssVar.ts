/* ============================================================
   CSS Variable Utilities

   Echarts and other canvas-based renderers cannot parse CSS
   custom properties like `var(--accent)` — they expect literal
   color strings. Use these helpers to resolve a CSS variable
   reference at render time so charts re-theme when the
   `data-theme` attribute on <html> changes.

   Callers should pass the FULL `var(--name)` form to
   resolveChartColor(), which extracts the variable name and
   looks it up on :root via getComputedStyle. Falls back to
   the supplied default if the variable is unset (SSR or no DOM).
   ============================================================ */

/** Read a CSS custom property value from :root. */
export function readCssVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/**
 * Resolve a color string, converting `var(--name)` references to
 * their concrete computed value. Non-CSS-var inputs pass through
 * unchanged.
 */
export function resolveChartColor(color: string, fallback: string): string {
  if (color.startsWith('var(')) {
    const varName = color.slice(4, -1).trim();
    return readCssVar(varName, fallback);
  }
  return color;
}

/**
 * Resolve a list of color strings. Convenience helper for series
 * palettes and split-area color arrays passed to echarts.
 */
export function resolveChartColors(colors: string[], fallback: string[]): string[] {
  return colors.map((c, i) => resolveChartColor(c, fallback[i] ?? fallback[0] ?? '#000'));
}