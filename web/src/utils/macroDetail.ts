/**
 * 全球速览指数详情页（/global/:code）纯函数工具集。
 *
 * 三个职责：
 *  1. 时间范围 key → start_date 换算（"全部" 返回 undefined，即不限制起点）；
 *  2. 后端 OHLC bar → KLineChart 需要的 OHLCV 结构映射（open 为 null 用 close 补齐）；
 *  3. 数值展示格式化（bp / 带单位数值）。
 *
 * 全部为纯函数，单测见 web/tests/macro-detail.test.ts。
 */

import type { MacroOhlcBar } from '@/types/macro';
import type { OHLCV } from '@/types/instrument';

/** 详情页时间范围 key（Radio.Group 的 value；中文 label 由页面组装）。 */
export type MacroRangeKey = '1M' | '3M' | '6M' | '1Y' | '3Y' | '5Y' | 'ALL';

/** 某 UTC 年月的总天数（用于月末日期减法时 clamp，避免 setMonth 溢出滚动）。 */
function daysInUtcMonth(year: number, monthIndex: number): number {
  return new Date(Date.UTC(year, monthIndex + 1, 0)).getUTCDate();
}

/** 格式化 Date 为 YYYY-MM-DD（UTC 口径，避免本地时区把日期拨回前一天）。 */
function toIsoDate(d: Date): string {
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/**
 * 时间范围 key → start_date（YYYY-MM-DD）。
 *
 * - 'ALL' / 未识别 key → undefined（后端按全量返回）；
 * - 月范围按日历月减（1M/3M/6M），年范围按日历年减（1Y/3Y/5Y）；
 * - 月末日期 clamp 到目标月最后一天（如 03-31 减 1 月 → 02-28，而非 03-03）。
 *
 * `now` 可注入固定时间便于测试，默认取当前时刻。
 */
export function rangeToStartDate(range: string, now: Date = new Date()): string | undefined {
  const months: Record<string, number> = { '1M': 1, '3M': 3, '6M': 6 };
  const years: Record<string, number> = { '1Y': 1, '3Y': 3, '5Y': 5 };

  const day = now.getUTCDate();
  let y = now.getUTCFullYear();
  let m = now.getUTCMonth();

  if (range in months) {
    m -= months[range];
  } else if (range in years) {
    y -= years[range];
  } else {
    // 'ALL' 与未识别 key：不限制起点
    return undefined;
  }

  // 归一化负数月份（借位到年份）
  const base = new Date(Date.UTC(y, m, 1));
  const clampedDay = Math.min(day, daysInUtcMonth(base.getUTCFullYear(), base.getUTCMonth()));
  base.setUTCDate(clampedDay);
  return toIsoDate(base);
}

/**
 * 后端 OHLC bars → KLineChart 的 OHLCV 结构。
 *
 * - date → trade_date；
 * - open 为 null 时用 close 补齐（FRED 日频序列常见，只有收盘价）；
 * - high/low 为 null 时取 open/close 的较大/较小值，保证蜡烛实体合法；
 * - volume 为 null 时补 0（KLineChart 的成交量直方图要求数值）。
 *
 * 输出按 trade_date 升序排序，符合 lightweight-charts 的时序要求。
 */
export function ohlcBarsToOHLCV(bars: MacroOhlcBar[]): OHLCV[] {
  return bars
    .filter((b) => b.date != null && b.close != null)
    .slice()
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
    .map((b) => {
      const open = b.open ?? b.close;
      const high = b.high ?? Math.max(open, b.close);
      const low = b.low ?? Math.min(open, b.close);
      return {
        trade_date: b.date,
        open,
        high,
        low,
        close: b.close,
        volume: b.volume ?? 0,
      };
    });
}

/**
 * 基点（bp）涨跌格式化：change_abs（百分点，如 0.035）×100 → "+3.5bp"。
 * null / NaN → '—'；0 → "0.0bp"（不带正号）。
 */
export function formatBp(changeAbs: number | null | undefined): string {
  if (changeAbs == null || Number.isNaN(changeAbs)) return '—';
  const bp = changeAbs * 100;
  return `${bp > 0 ? '+' : ''}${bp.toFixed(1)}bp`;
}

/**
 * 带单位的数值格式化（与 GlobalMarkets 速览页 formatValue 口径一致）：
 * - 单位 '%' → 两位小数 + '%'；
 * - 绝对值 ≥ 1000 → 千分位、最多两位小数；
 * - 其它 → 两位小数；null / NaN → '—'。
 */
export function formatMacroValue(
  value: number | null | undefined,
  unit?: string,
): string {
  if (value == null || Number.isNaN(value)) return '—';
  if (unit === '%') return `${value.toFixed(2)}%`;
  if (Math.abs(value) >= 1000) {
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return value.toFixed(2);
}
