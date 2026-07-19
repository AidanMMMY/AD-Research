import { formatDateTime as formatDateTimeTz } from './datetime';

/** 统一空值显示符号（em-dash） */
export const NULL_PLACEHOLDER = '—';

/**
 * 格式化百分比（小数语义）：输入 v 期望是分数（如 0.025 = 2.5%）。
 * 适用场景：后端的 ``return_1m/return_3m/return_1y`` 这类由 ``pct_change``
 * 派生的指标字段（A 股/ETF/指数 ``etf_indicator`` 等）。
 *
 * ⚠️ 不适用于后端的 ``change_pct`` 字段——它的语义是百分比本身
 * （如 1.5 = +1.5%），请改用 ``formatPercentRaw``。
 */
export function formatPercent(v: number | null | undefined, decimals = 2, signed = true): string {
  if (v == null || Number.isNaN(v)) return NULL_PLACEHOLDER;
  const pct = v * 100;
  const sign = signed && pct > 0 ? '+' : '';
  return `${sign}${pct.toFixed(decimals)}%`;
}

/**
 * 格式化百分比（原始语义）：输入 v 已经是百分比本身（如 1.5 = +1.5%）。
 * 适用场景：SSE ``/stream/prices`` 的 ``change_pct`` / ``/macro/indices/global``
 * 的 ``change_pct`` / 加密货币 ``change_pct`` / 期货 ``settle_change_pct`` 等
 * 由后端 ``(latest - prev) / prev * 100`` 落地的字段。
 *
 * 配套 UI 组件：``<ReturnTagPct value={x.change_pct} />``。
 * 若搭配小数语义的字段请用 ``formatPercent`` + ``<ReturnTag>``，二者
 * 绝对不能混用，否则涨跌幅会被错误放大 100 倍（参见 2026-07-19
 * 首页市场脉搏 -100.99% / -178.48% / -636.72% 等 bug）。
 */
export function formatPercentRaw(v: number | null | undefined, decimals = 2, signed = true): string {
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
