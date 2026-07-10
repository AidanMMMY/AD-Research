import { formatDateTime as formatDateTimeTz } from './datetime';

/** 统一空值显示符号（em-dash） */
export const NULL_PLACEHOLDER = '—';

/** 格式化百分比，signed=true 时正数显示 + 号 */
export function formatPercent(v: number | null | undefined, decimals = 2, signed = true): string {
  if (v == null || Number.isNaN(v)) return NULL_PLACEHOLDER;
  const sign = signed && v > 0 ? '+' : '';
  return `${sign}${v.toFixed(decimals)}%`;
}

/** 格式化千分位数字 */
export function formatNumber(v: number | null | undefined, decimals = 2): string {
  if (v == null || Number.isNaN(v)) return NULL_PLACEHOLDER;
  return v.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function formatAmount(value?: number | null): string {
  if (value === undefined || value === null) return NULL_PLACEHOLDER;
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

/** 统一日期时间格式（Asia/Shanghai 时区） */
export function formatDateTime(iso: string | number | null | undefined, fmt = 'YYYY-MM-DD HH:mm:ss'): string {
  if (!iso) return NULL_PLACEHOLDER;
  return formatDateTimeTz(iso, fmt, NULL_PLACEHOLDER);
}

/** RSI / 技术指标保留 1 位小数 */
export function formatIndicator(v: number | null | undefined, decimals = 1): string {
  if (v == null || Number.isNaN(v)) return NULL_PLACEHOLDER;
  return v.toFixed(decimals);
}
