/**
 * Sector rotation domain types.
 *
 * Re-exports the API client types so feature code can import from
 * `@/types/sector_rotation` (the project's convention — see
 * `@/types/instrument`, `@/types/screen`).
 *
 * Field-level docs live in `app/schemas/sector_rotation.py`.
 */

/** Industry classification system: GICS (global default) or 申万 (A-share). */
export type SectorClassification = 'GICS' | 'SW';

export interface SectorScope {
  market: 'A股';
  instrument_types: Array<'ETF' | 'STOCK'>;
  classification: SectorClassification;
}

export interface SectorPerformance {
  sector: string;
  count: number;
  stock_count: number;
  etf_count: number;
  return_1w: number;
  return_1m: number;
  return_3m: number;
  return_6m: number;
  return_1y: number;
  sharpe_1y: number;
  volatility_20d: number;
  rsi14: number;
  amount_total: number;
  relative_strength_1w: number;
  relative_strength_1m: number;
  relative_strength_3m: number;
  momentum_rank: number;
  // ----------------------------------------------------------------
  // Phase 3 (added 2026-07-19): SW 模式下，return_* 已切换为申万一级
  // 指数官方回报；constituent_return_* 保留等权 ETF+STOCK 回报作为
  // 对照。return_source 标记当前 return_* 的来源。
  //
  // - return_source: "official_index"           — return_* 来自官方指数
  //                         (SW 模式 + sw_industry_index_return 有行)
  //                 : "constituents_equal_weight" — return_* 来自等权平均
  //                         (GICS 模式或 SW 模式但缺官方行)
  // - sw_l1_code: 申万一级行业代码 (e.g. "801080"), 仅 SW 模式有
  // - official_close: 申万指数当日收盘点位, 仅 SW 模式有
  // - constituent_return_*: 等权回报对照, 仅 SW 模式有
  // ----------------------------------------------------------------
  return_source?: 'official_index' | 'constituents_equal_weight';
  sw_l1_code?: string | null;
  official_close?: number | null;
  constituent_return_1w?: number | null;
  constituent_return_1m?: number | null;
  constituent_return_3m?: number | null;
  constituent_return_6m?: number | null;
  constituent_return_1y?: number | null;
}

export interface RotationSignal {
  sector: string;
  type: 'up' | 'down';
  message: string;
  current_rank: number;
  previous_rank: number;
  rank_change: number;
}

export interface MarketAverage {
  return_1w: number;
  return_1m: number;
  return_3m: number;
  return_6m: number;
  return_1y: number;
  sharpe_1y: number;
}

export interface SectorRotationData {
  trade_date: string | null;
  scope: SectorScope;
  sectors: SectorPerformance[];
  market_avg: MarketAverage | null;
  rotation_signals: RotationSignal[];
}

export interface SectorListItem {
  sector: string;
  count: number;
  stock_count: number;
  etf_count: number;
}

export interface SectorListData {
  items: SectorListItem[];
}

// ---------------------------------------------------------------------------
// Constituents view (added 2026-07-09)
// ---------------------------------------------------------------------------

export type SectorConstituentType = 'ETF' | 'STOCK';

export interface SectorConstituent {
  code: string;
  name: string;
  instrument_type: SectorConstituentType;
  /** Resolved GICS sector (echoed from the server). */
  resolved_sector: string;
  /** Weight in CNY 元. null when the upstream data is missing. */
  weight: number | null;
  weight_unit: '元';
  /** '市值' for STOCK, '规模' for ETF — drives the column header. */
  weight_label: '市值' | '规模';
  return_1w: number | null;
  return_1m: number | null;
  return_3m: number | null;
  return_6m: number | null;
  return_1y: number | null;
  sharpe_1y: number | null;
  rsi14: number | null;
  amount_total: number | null;
}

export interface SectorConstituentsData {
  sector: string;
  trade_date: string | null;
  count: number;
  total_in_sector: number;
  items: SectorConstituent[];
}

/** Display columns used by the heatmap & detail table. */
export type SectorReturnPeriod = '1w' | '1m' | '3m' | '6m' | '1y';

export const SECTOR_RETURN_PERIODS: SectorReturnPeriod[] = ['1w', '1m', '3m', '6m', '1y'];

export const SECTOR_RETURN_LABELS: Record<SectorReturnPeriod, string> = {
  '1w': '1周',
  '1m': '1月',
  '3m': '3月',
  '6m': '6月',
  '1y': '1年',
};