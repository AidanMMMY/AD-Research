/* ============================================================
   Color Utilities — Hybrid Theme (Swiss + Bento)

   Supports dual color conventions:
   - china: red=up/gain, green=down/loss (A-share convention)
   - us:    green=up/gain, red=down/loss (Western convention)

   CRITICAL: CSS layer (theme.css) already handles convention switching
   via [data-color-convention] on <html>.  JS functions below MUST NOT
   flip colors — they always return var(--color-rise) for positive and
   var(--color-fall) for negative.  The CSS layer owns the swap.
   ============================================================ */

export type ColorConvention = 'china' | 'us';

/** Get the "positive" color (up/gain).
 *  CSS layer handles convention swap — always returns rise. */
export function getUpColor(_convention: ColorConvention = 'china'): string {
  return 'var(--color-rise)';
}

/** Get the "negative" color (down/loss).
 *  CSS layer handles convention swap — always returns fall. */
export function getDownColor(_convention: ColorConvention = 'china'): string {
  return 'var(--color-fall)';
}

/** Get text color for return value */
export function getReturnColor(value?: number | null, _convention: ColorConvention = 'china'): string {
  if (value === undefined || value === null) return 'var(--text-tertiary)';
  return value >= 0 ? getUpColor() : getDownColor();
}

/** Get background color for return tag */
export function getReturnBgColor(value?: number | null, _convention: ColorConvention = 'china'): string {
  if (value === undefined || value === null) return 'var(--bg-input)';
  return value >= 0 ? 'var(--color-rise-dim)' : 'var(--color-fall-dim)';
}

/** Get border color for return tag */
export function getReturnBorderColor(value?: number | null, _convention: ColorConvention = 'china'): string {
  if (value === undefined || value === null) return 'var(--border-default)';
  return value >= 0 ? 'var(--color-rise-border)' : 'var(--color-fall-border)';
}

/** Get color for score progress bar */
export function getScoreColor(score: number): string {
  if (score >= 80) return 'var(--score-excellent)';
  if (score >= 60) return 'var(--score-good)';
  if (score >= 40) return 'var(--score-average)';
  return 'var(--score-bad)';
}

/** Get signal type color */
export function getSignalColor(type: string): string {
  const map: Record<string, string> = {
    BUY: 'var(--color-rise)',
    SELL: 'var(--color-fall)',
    HOLD: 'var(--color-warning)',
  };
  return map[type] || 'var(--text-tertiary)';
}

/** Get signal background color */
export function getSignalBgColor(type: string): string {
  const map: Record<string, string> = {
    BUY: 'var(--color-rise-dim)',
    SELL: 'var(--color-fall-dim)',
    HOLD: 'var(--color-warning-dim)',
  };
  return map[type] || 'var(--bg-input)';
}
