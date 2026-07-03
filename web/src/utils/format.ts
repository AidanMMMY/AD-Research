import { formatDateTime as formatDateTimeTz } from './datetime';

export function formatPercent(value?: number | null, digits = 2): string {
  if (value === undefined || value === null) return '-';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(digits)}%`;
}

export function formatNumber(value?: number | null, digits = 2): string {
  if (value === undefined || value === null) return '-';
  return value.toFixed(digits);
}

export function formatAmount(value?: number | null): string {
  if (value === undefined || value === null) return '-';
  if (value >= 1e8) return `${(value / 1e8).toFixed(1)}亿`;
  if (value >= 1e4) return `${(value / 1e4).toFixed(1)}万`;
  return value.toFixed(0);
}

// Re-export the timezone-aware formatters so existing callers of
// ``formatDate`` / ``formatDateTime`` automatically pick up the UTC
// fix in ``utils/datetime.ts`` without touching the call sites.
export function formatDate(date?: string | null, fmt = 'YYYY-MM-DD'): string {
  return formatDateTimeTz(date, fmt);
}

export function formatDateTime(date?: string | null): string {
  return formatDateTimeTz(date, 'YYYY-MM-DD HH:mm');
}
