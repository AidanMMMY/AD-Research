/**
 * Sector rotation domain types.
 *
 * Re-exports the API client types so feature code can import from
 * `@/types/sector_rotation` (the project's convention — see
 * `@/types/instrument`, `@/types/screen`).
 *
 * Field-level docs live in `app/schemas/sector_rotation.py`.
 */

export interface SectorScope {
  market: 'A股';
  instrument_types: Array<'ETF' | 'STOCK'>;
  classification: 'GICS';
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