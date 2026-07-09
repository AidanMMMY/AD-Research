import { useMemo } from 'react';

/**
 * Stable keys for the type-aware sections that render below the core
 * (Hero / K-line / Key Stats / Indicators) area of `InstrumentDetail`.
 *
 * To add a new type-aware module (e.g. financial highlights for stocks,
 * on-chain market data for cryptos):
 *   1. Add a new key to this union.
 *   2. Inject `{ key, visible: true, order }` from your feature module's
 *      hook (wrap or replace `useInstrumentModules`).
 *   3. In `InstrumentDetail/index.tsx`, render a panel keyed off
 *      `useModuleVisibility(modules, 'your-key')`.
 *
 * Keep keys stable — they are used as React `key`s for the rendered
 * fragments and may be referenced by deep-links / analytics events.
 */
export type InstrumentModuleKey =
  | 'holdings'        // ETF 前十大持仓
  | 'valuation'       // 估值数据（A 股 STOCK 默认开启）
  | 'financials'      // 财务亮点（预留扩展位 — 由并行任务补 STOCK/CRYPTO）
  | 'market-data'     // 市场数据（预留扩展位 — 由并行任务补 CRYPTO）
  | 'score'           // 综合评分
  | 'ai'              // AI 分析（研报 / 情绪）
  | 'news';           // 相关新闻

export interface InstrumentModuleState {
  key: InstrumentModuleKey;
  /**
   * Whether this section should render for the given instrument. Pages
   * should treat `false` as "skip" and `true` as "render in `order`".
   */
  visible: boolean;
  /**
   * Render order — lower numbers appear higher on the page. Default 100.
   * Sections with the same order keep the relative order of this array.
   */
  order?: number;
  /** Optional override of the human-readable section title. */
  title?: string;
}

/**
 * Default visibility rules for the type-aware modules.
 *
 *   ETF    → holdings + score + ai + news
 *   STOCK  → valuation + score + ai + news
 *   CRYPTO → score + ai + news（financials / market-data 由后续并行任务开启）
 *
 * Why a hook (and not just `if (isStock) …` inline)?
 * `InstrumentDetail` is the integration point for many parallel feature
 * tracks. Centralising the visibility decision here lets new sections
 * drop in without touching the page file. Wrap or replace this hook
 * from the feature module to inject extra `visible: true` entries.
 */
export function useInstrumentModules(
  _code: string | undefined,
  instrumentType?: string,
): InstrumentModuleState[] {
  return useMemo(() => {
    const type = (instrumentType || '').toUpperCase();
    return [
      // ETF-only: top-10 holdings.
      { key: 'holdings', visible: type === 'ETF', order: 100 },
      // A-share stock-only: 估值数据.
      { key: 'valuation', visible: type === 'STOCK', order: 110 },
      // Extension points — invisible by default; flip on from the
      // parallel "type-specific modules" task.
      { key: 'financials', visible: false, order: 120 },
      { key: 'market-data', visible: false, order: 130 },
      // Universal modules.
      { key: 'score', visible: true, order: 200 },
      { key: 'ai', visible: true, order: 210 },
      { key: 'news', visible: true, order: 220 },
    ];
  }, [instrumentType]);
}

/** Convenience selector — returns true when the section should render. */
export function moduleIsVisible(
  modules: InstrumentModuleState[],
  key: InstrumentModuleKey,
): boolean {
  return modules.find((m) => m.key === key)?.visible ?? false;
}

/** Sort helper — pages can map over `modules` in render order. */
export function sortModules(modules: InstrumentModuleState[]): InstrumentModuleState[] {
  return [...modules].sort((a, b) => (a.order ?? 100) - (b.order ?? 100));
}