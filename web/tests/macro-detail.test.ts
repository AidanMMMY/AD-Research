/**
 * Unit tests for `src/utils/macroDetail.ts`（全球速览指数详情页纯函数）。
 *
 * 覆盖：
 *  - rangeToStartDate：月/年范围换算、"全部" 返回 undefined、月末 clamp；
 *  - ohlcBarsToOHLCV：键映射、open null → close 补齐、high/low null 补齐、排序；
 *  - formatBp：bp 格式化（+3.5bp / -2.0bp / 0 / null）；
 *  - formatMacroValue：带单位数值格式化。
 */
import { describe, expect, it } from 'vitest';
import {
  formatBp,
  formatMacroValue,
  ohlcBarsToOHLCV,
  rangeToStartDate,
} from '@/utils/macroDetail';

describe('rangeToStartDate', () => {
  // 固定 "now" = 2026-07-29（UTC）
  const now = new Date(Date.UTC(2026, 6, 29, 10, 0, 0));

  it('returns undefined for 全部 (ALL)', () => {
    expect(rangeToStartDate('ALL', now)).toBeUndefined();
  });

  it('returns undefined for unrecognised keys', () => {
    expect(rangeToStartDate('2Y', now)).toBeUndefined();
    expect(rangeToStartDate('', now)).toBeUndefined();
  });

  it('subtracts calendar months for month ranges', () => {
    expect(rangeToStartDate('1M', now)).toBe('2026-06-29');
    expect(rangeToStartDate('3M', now)).toBe('2026-04-29');
    expect(rangeToStartDate('6M', now)).toBe('2026-01-29');
  });

  it('subtracts calendar years for year ranges', () => {
    expect(rangeToStartDate('1Y', now)).toBe('2025-07-29');
    expect(rangeToStartDate('3Y', now)).toBe('2023-07-29');
    expect(rangeToStartDate('5Y', now)).toBe('2021-07-29');
  });

  it('clamps month-end dates instead of rolling into the next month', () => {
    // 2026-03-31 减 1 个月 → 2026-02-28（而非 setMonth 溢出的 03-03）
    const monthEnd = new Date(Date.UTC(2026, 2, 31));
    expect(rangeToStartDate('1M', monthEnd)).toBe('2026-02-28');
    // 闰年：2024-03-31 减 1 个月 → 2024-02-29
    const leapMonthEnd = new Date(Date.UTC(2024, 2, 31));
    expect(rangeToStartDate('1M', leapMonthEnd)).toBe('2024-02-29');
  });

  it('handles month subtraction across year boundary', () => {
    // 2026-01-15 减 3 个月 → 2025-10-15
    const jan = new Date(Date.UTC(2026, 0, 15));
    expect(rangeToStartDate('3M', jan)).toBe('2025-10-15');
  });
});

describe('ohlcBarsToOHLCV', () => {
  it('maps date→trade_date and carries OHLCV through', () => {
    const out = ohlcBarsToOHLCV([
      { date: '2026-07-28', open: 100, high: 105, low: 99, close: 103, volume: 1234 },
    ]);
    expect(out).toEqual([
      { trade_date: '2026-07-28', open: 100, high: 105, low: 99, close: 103, volume: 1234 },
    ]);
  });

  it('fills null open with close, and null high/low from open/close bounds', () => {
    const out = ohlcBarsToOHLCV([
      { date: '2026-07-28', open: null, high: null, low: null, close: 4.25, volume: null },
    ]);
    expect(out).toEqual([
      { trade_date: '2026-07-28', open: 4.25, high: 4.25, low: 4.25, close: 4.25, volume: 0 },
    ]);
  });

  it('derives high/low as max/min of open and close when only they are null', () => {
    const out = ohlcBarsToOHLCV([
      { date: '2026-07-28', open: 10, high: null, low: null, close: 12, volume: 5 },
    ]);
    expect(out[0].high).toBe(12);
    expect(out[0].low).toBe(10);
  });

  it('sorts ascending by date (lightweight-charts requirement)', () => {
    const out = ohlcBarsToOHLCV([
      { date: '2026-07-28', open: 1, high: 1, low: 1, close: 2, volume: 0 },
      { date: '2026-07-27', open: 1, high: 1, low: 1, close: 1, volume: 0 },
    ]);
    expect(out.map((b) => b.trade_date)).toEqual(['2026-07-27', '2026-07-28']);
  });

  it('drops bars without a usable date or close', () => {
    const out = ohlcBarsToOHLCV([
      { date: '2026-07-28', open: 1, high: 1, low: 1, close: null as unknown as number, volume: 0 },
      { date: '2026-07-29', open: 1, high: 1, low: 1, close: 2, volume: 0 },
    ]);
    expect(out).toHaveLength(1);
    expect(out[0].trade_date).toBe('2026-07-29');
  });
});

describe('formatBp', () => {
  it('formats positive deltas with a plus sign', () => {
    expect(formatBp(0.035)).toBe('+3.5bp');
  });

  it('formats negative deltas without an extra plus', () => {
    expect(formatBp(-0.02)).toBe('-2.0bp');
  });

  it('formats zero without a sign', () => {
    expect(formatBp(0)).toBe('0.0bp');
  });

  it('renders the placeholder for null / NaN', () => {
    expect(formatBp(null)).toBe('—');
    expect(formatBp(undefined)).toBe('—');
    expect(formatBp(Number.NaN)).toBe('—');
  });
});

describe('formatMacroValue', () => {
  it('appends % when the unit is %', () => {
    expect(formatMacroValue(4.256, '%')).toBe('4.26%');
  });

  it('uses thousands separators for large values', () => {
    expect(formatMacroValue(43210.567, 'pt')).toBe('43,210.57');
  });

  it('keeps two decimals for small values', () => {
    expect(formatMacroValue(103.456, 'JPY')).toBe('103.46');
  });

  it('renders the placeholder for null / NaN', () => {
    expect(formatMacroValue(null, '%')).toBe('—');
    expect(formatMacroValue(undefined)).toBe('—');
    expect(formatMacroValue(Number.NaN)).toBe('—');
  });
});
