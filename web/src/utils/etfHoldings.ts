/**
 * ETF 持仓共享工具函数（2026-07-27 独立页 → 详情页合并）。
 *
 * 原本散落在 ``pages/EtfHoldingsHistory/index.tsx`` 的纯函数，现在由
 * 深链页 (EtfHoldingsHistory) 与详情页持仓模块 (EtfHoldingsAnalytics)
 * 共用，避免两处实现漂移。
 */
import type { ETFHoldingItem } from '@/types/instrument';
import { NULL_PLACEHOLDER } from '@/utils/format';

/** Format a weight as a percent string (decimal → %). */
export function fmtWeight(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return NULL_PLACEHOLDER;
  return `${(v * 100).toFixed(digits)}%`;
}

/** Compact human-readable number (e.g. 12_345_678 → 1234.57万). */
export function fmtShares(v: number | null | undefined): string {
  if (v === null || v === undefined) return NULL_PLACEHOLDER;
  if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(2)} 亿`;
  if (Math.abs(v) >= 1e4) return `${(v / 1e4).toFixed(2)} 万`;
  return v.toFixed(0);
}

/** Bare code without exchange suffix — grouping key for holdings dedupe. */
export function bareCodeKey(code: string): string {
  return code.split('.')[0].toUpperCase();
}

/** A code is navigable to the instrument detail page only when suffixed. */
export function isNavigableCode(code: string): boolean {
  return code.includes('.');
}

/**
 * Dedupe holdings by normalised code: '300750' and '300750.SZ' are the same
 * instrument, so collapse them into one row keyed on the suffixed standard
 * code. On conflict prefer the row from the latest disclosure date, then
 * back-fill null weight / shares / market value from the losing row.
 *
 * 这是防御层——pipeline load 阶段已统一代码格式 (2026-07 commit a163d6e)，
 * 但历史脏数据 / 边界源仍可能同时吐出 bare + suffixed 两种行。
 */
export function mergeHoldings(items: ETFHoldingItem[]): ETFHoldingItem[] {
  const byKey = new Map<string, ETFHoldingItem>();
  for (const item of items) {
    const key = bareCodeKey(item.holding_code);
    const existing = byKey.get(key);
    if (!existing) {
      byKey.set(key, item);
      continue;
    }
    const preferItem =
      (isNavigableCode(item.holding_code) && !isNavigableCode(existing.holding_code)) ||
      (item.holdings_as_of_date ?? '') > (existing.holdings_as_of_date ?? '');
    const winner = preferItem ? item : existing;
    const loser = preferItem ? existing : item;
    byKey.set(key, {
      ...winner,
      holding_name: winner.holding_name ?? loser.holding_name,
      weight: winner.weight ?? loser.weight,
      shares: winner.shares ?? loser.shares,
      market_value: winner.market_value ?? loser.market_value,
    });
  }
  return Array.from(byKey.values());
}
