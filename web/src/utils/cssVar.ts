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
 * Strict CSS var reader — returns the computed value or '' when missing.
 * Use this when the caller MUST know whether the token is defined (e.g.
 * AntD theme configuration), so silent dark-fallback doesn't masquerade
 * as a valid value when the token is absent in the active theme.
 *
 * Emits a one-time console.warn per missing token so silent failure
 * becomes visible at dev time.
 */
const _warnedMissingTokens = new Set<string>();
export function readCssVarStrict(name: string): string {
  if (typeof window === 'undefined') return '';
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  if (!value && !_warnedMissingTokens.has(name)) {
    _warnedMissingTokens.add(name);
    // eslint-disable-next-line no-console
    console.warn(
      `[cssVar] Token ${name} is not defined on :root for the active theme. ` +
      'Check theme.css — both :root (light base) and :root[data-theme="dark"] ' +
      'must declare this token, otherwise consumers fall back to defaults.'
    );
  }
  return value;
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
  return colors.map((c, i) => resolveChartColor(c, fallback[i] ?? fallback[0] ?? readCssVar('--text-primary', '#000')));
}