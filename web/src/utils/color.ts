/* ============================================================
   Color Utilities — Modern Dark Tech Theme

   Supports dual color conventions:
   - china: red=up/gain, green=down/loss (A-share convention)
   - us:    green=up/gain, red=down/loss (Western convention)

   All color functions accept an optional `convention` parameter.
   Default is 'china' for backward compatibility.
   ============================================================ */

export type ColorConvention = 'china' | 'us';

/** Get the "positive" color (up/gain) for the given convention */
export function getUpColor(convention: ColorConvention = 'china'): string {
  return convention === 'us' ? '#22c55e' : '#ef4444';
}

/** Get the "negative" color (down/loss) for the given convention */
export function getDownColor(convention: ColorConvention = 'china'): string {
  return convention === 'us' ? '#ef4444' : '#22c55e';
}

/** Get text color for return value */
export function getReturnColor(value?: number | null, convention: ColorConvention = 'china'): string {
  if (value === undefined || value === null) return '#64748b';
  return value >= 0 ? getUpColor(convention) : getDownColor(convention);
}

/** Get background color for return tag */
export function getReturnBgColor(value?: number | null, convention: ColorConvention = 'china'): string {
  if (value === undefined || value === null) return 'rgba(255,255,255,0.03)';
  const color = value >= 0 ? getUpColor(convention) : getDownColor(convention);
  // Extract RGB from hex to create rgba with opacity
  const hex = color.replace('#', '');
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, 0.12)`;
}

/** Get border color for return tag */
export function getReturnBorderColor(value?: number | null, convention: ColorConvention = 'china'): string {
  if (value === undefined || value === null) return 'rgba(255,255,255,0.06)';
  const color = value >= 0 ? getUpColor(convention) : getDownColor(convention);
  const hex = color.replace('#', '');
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, 0.25)`;
}

/** Get color for score progress bar (convention-independent) */
export function getScoreColor(score: number): string {
  if (score >= 80) return '#22c55e';
  if (score >= 60) return '#84cc16';
  if (score >= 40) return '#eab308';
  return '#ef4444';
}

/** Get signal type color */
export function getSignalColor(type: string): string {
  const map: Record<string, string> = {
    BUY: '#ef4444',
    SELL: '#22c55e',
    HOLD: '#eab308',
  };
  return map[type] || '#64748b';
}

/** Get signal background color */
export function getSignalBgColor(type: string): string {
  const map: Record<string, string> = {
    BUY: 'rgba(239, 68, 68, 0.12)',
    SELL: 'rgba(34, 197, 94, 0.12)',
    HOLD: 'rgba(234, 179, 8, 0.12)',
  };
  return map[type] || 'rgba(255,255,255,0.03)';
}
