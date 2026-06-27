/* ============================================================
   Color Utilities — Hybrid Theme (Swiss + Bento)

   Supports dual color conventions:
   - china: red=up/gain, green=down/loss (A-share convention)
   - us:    green=up/gain, red=down/loss (Western convention)

   All functions return CSS variables for runtime theme compatibility.
   ============================================================ */

export type ColorConvention = 'china' | 'us';

/** Get the "positive" color (up/gain) for the given convention */
export function getUpColor(convention: ColorConvention = 'china'): string {
  return convention === 'us' ? 'var(--color-fall)' : 'var(--color-rise)';
}

/** Get the "negative" color (down/loss) for the given convention */
export function getDownColor(convention: ColorConvention = 'china'): string {
  return convention === 'us' ? 'var(--color-rise)' : 'var(--color-fall)';
}

/** Get text color for return value */
export function getReturnColor(value?: number | null, convention: ColorConvention = 'china'): string {
  if (value === undefined || value === null) return 'var(--text-tertiary)';
  return value >= 0 ? getUpColor(convention) : getDownColor(convention);
}

/** Get background color for return tag */
export function getReturnBgColor(value?: number | null, convention: ColorConvention = 'china'): string {
  if (value === undefined || value === null) return 'var(--bg-input)';
  return value >= 0
    ? (convention === 'us' ? 'var(--color-fall-dim)' : 'var(--color-rise-dim)')
    : (convention === 'us' ? 'var(--color-rise-dim)' : 'var(--color-fall-dim)');
}

/** Get border color for return tag */
export function getReturnBorderColor(value?: number | null, convention: ColorConvention = 'china'): string {
  if (value === undefined || value === null) return 'var(--border-default)';
  return value >= 0
    ? (convention === 'us' ? 'var(--color-fall-border)' : 'var(--color-rise-border)')
    : (convention === 'us' ? 'var(--color-rise-border)' : 'var(--color-fall-border)');
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
