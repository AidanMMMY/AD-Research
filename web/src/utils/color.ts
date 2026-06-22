/* ============================================================
   Color Utilities — Modern Dark Tech Theme
   ============================================================ */

/** Get text color for return value (China A-share: red=up, green=down) */
export function getReturnColor(value?: number | null): string {
  if (value === undefined || value === null) return '#64748b';
  return value >= 0 ? '#ef4444' : '#22c55e';
}

/** Get background color for return tag */
export function getReturnBgColor(value?: number | null): string {
  if (value === undefined || value === null) return 'rgba(255,255,255,0.03)';
  return value >= 0 ? 'rgba(239, 68, 68, 0.12)' : 'rgba(34, 197, 94, 0.12)';
}

/** Get border color for return tag */
export function getReturnBorderColor(value?: number | null): string {
  if (value === undefined || value === null) return 'rgba(255,255,255,0.06)';
  return value >= 0 ? 'rgba(239, 68, 68, 0.25)' : 'rgba(34, 197, 94, 0.25)';
}

/** Get color for score progress bar */
export function getScoreColor(score: number): string {
  if (score >= 80) return '#22c55e';
  if (score >= 60) return '#84cc16';
  if (score >= 40) return '#eab308';
  return '#ef4444';
}

/** Get gradient for score */
export function getScoreGradient(score: number): string {
  if (score >= 80) return 'linear-gradient(90deg, #22c55e, #4ade80)';
  if (score >= 60) return 'linear-gradient(90deg, #84cc16, #a3e635)';
  if (score >= 40) return 'linear-gradient(90deg, #eab308, #facc15)';
  return 'linear-gradient(90deg, #ef4444, #f87171)';
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
