import { useQuery, useQueryClient } from '@tanstack/react-query';
import client from './client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Sort direction helpers. Backend expects `field` or `-field` (leading
 *  minus = desc). Kept here so call sites stay type-safe. */
export type SortDir = 'asc' | 'desc';

export interface MarketFundFlow {
  trade_date: string;
  sh_main_net_inflow: number;
  sz_main_net_inflow: number;
  sh_main_net_pct: number;
  sz_main_net_pct: number;
  total_main_net_inflow?: number;
  total_main_net_pct?: number;
}

export type FundFlowSource = 'akshare' | 'eastmoney';

export interface IndividualFundFlow {
  ts_code: string;
  name?: string | null;
  trade_date: string;
  main_net_inflow: number;
  main_net_pct: number;
  super_large_net: number;
  super_large_pct: number;
  large_net: number;
  large_pct: number;
  medium_net: number;
  medium_pct: number;
  small_net: number;
  small_pct: number;
  source: FundFlowSource;
}

export type SectorType = '行业' | '概念' | '地域';

export interface SectorFundFlow {
  sector_name: string;
  sector_type: SectorType;
  trade_date: string;
  main_net_inflow: number;
  main_net_pct: number;
  super_large_net: number;
  large_net: number;
  leading_stock?: string | null;
}

export interface EtfFundFlow {
  ts_code: string;
  name?: string | null;
  trade_date: string;
  price: number;
  net_value: number;
  premium_rate: number;
  shares_outstanding: number;
  shares_change: number;
  turnover: number;
  inferred_net_inflow: number;
}

export interface FlowSignal {
  ts_code: string;
  name?: string | null;
  trade_date: string;
  main_net_inflow: number;
  margin_net_change: number;
  lhb_net_buy: number;
  shareholder_count_change: number;
  ah_premium: number;
  block_trade_net: number;
  composite_score: number;
  score_breakdown: Record<string, number>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Convert a `SortDir` to the backend's `field` / `-field` notation.
 * Backend uses FastAPI's `sort` query param which honors leading minus as
 * descending. Centralizing this avoids `-1` / `desc` / `false` drift across
 * call sites.
 */
export function sortField(field: string, dir: SortDir = 'desc'): string {
  return dir === 'desc' ? `-${field}` : field;
}

// ---------------------------------------------------------------------------
// API client
// ---------------------------------------------------------------------------

export interface IndividualListParams {
  trade_date?: string;
  sort?: string;
  limit?: number;
  market?: string;
}

export interface SectorListParams {
  trade_date?: string;
  sector_type?: SectorType;
  sort?: string;
}

export interface EtfListParams {
  trade_date?: string;
  sort?: string;
  limit?: number;
}

export interface SignalListParams {
  trade_date?: string;
  sort?: string;
  limit?: number;
}

export const fundFlowApi = {
  /**
   * Aggregated exchange-level main-fund net inflow for a given trade date.
   * SH + SZ main flows plus their share-of-turnover percentage.
   */
  market(trade_date?: string): Promise<{ data: MarketFundFlow }> {
    return client.get<MarketFundFlow>('/fund-flow/market', { params: { trade_date } });
  },

  /**
   * Per-stock main-fund flow ranked by `sort`. Defaults to
   * `-main_net_inflow` (top inflow). Optional `market` filter narrows
   * to SH / SZ / STAR / ChiNext / BSE — caller decides which subset to
   * surface (the backend is permissive about the value).
   */
  individualList(params: IndividualListParams = {}): Promise<{ data: IndividualFundFlow[] }> {
    return client.get<IndividualFundFlow[]>('/fund-flow/individual', { params });
  },

  /** Per-stock daily flow history for the trailing N trading days. */
  individualHistory(tsCode: string, days = 60): Promise<{ data: IndividualFundFlow[] }> {
    return client.get<IndividualFundFlow[]>(
      `/fund-flow/individual/${encodeURIComponent(tsCode)}`,
      { params: { days } },
    );
  },

  /**
   * Per-sector flow ranked by `sort`. `sector_type` is a literal string
   * the backend stores as-is ("行业" / "概念" / "地域") so we keep the
   * same casing when round-tripping.
   */
  sectorList(params: SectorListParams = {}): Promise<{ data: SectorFundFlow[] }> {
    return client.get<SectorFundFlow[]>('/fund-flow/sector', { params });
  },

  /** Per-ETF inferred flow (shares-change × price) and premium/discount. */
  etfList(params: EtfListParams = {}): Promise<{ data: EtfFundFlow[] }> {
    return client.get<EtfFundFlow[]>('/fund-flow/etf', { params });
  },

  /**
   * Composite flow signals — cross-source score in `[-100, +100]` plus a
   * breakdown of contributing drivers. Higher = more inflow conviction.
   */
  signalsList(params: SignalListParams = {}): Promise<{ data: FlowSignal[] }> {
    return client.get<FlowSignal[]>('/fund-flow/signals', { params });
  },

  signalsHistory(tsCode: string, days = 30): Promise<{ data: FlowSignal[] }> {
    return client.get<FlowSignal[]>(
      `/fund-flow/signals/${encodeURIComponent(tsCode)}`,
      { params: { days } },
    );
  },
};

// ---------------------------------------------------------------------------
// React Query hooks (used by the page)
// ---------------------------------------------------------------------------

const SHARED_OPTIONS = {
  staleTime: 60_000,
  refetchOnWindowFocus: false,
} as const;

/** Today's main-fund exchange-level flow. Optional `trade_date` for history. */
export function useFundFlowMarket(trade_date?: string) {
  return useQuery({
    queryKey: ['fund-flow', 'market', trade_date ?? 'today'],
    queryFn: () => fundFlowApi.market(trade_date).then((r) => r.data),
    ...SHARED_OPTIONS,
  });
}

/** Per-stock flow list. The page passes its own params object. */
export function useFundFlowIndividual(params: IndividualListParams) {
  return useQuery({
    queryKey: ['fund-flow', 'individual', params],
    queryFn: () => fundFlowApi.individualList(params).then((r) => r.data ?? []),
    ...SHARED_OPTIONS,
  });
}

/** Per-stock daily history (used by the detail placeholder + sparkline). */
export function useFundFlowIndividualHistory(tsCode: string | null, days = 60) {
  return useQuery({
    queryKey: ['fund-flow', 'individual-history', tsCode, days],
    queryFn: () =>
      tsCode
        ? fundFlowApi.individualHistory(tsCode, days).then((r) => r.data ?? [])
        : Promise.resolve([]),
    enabled: !!tsCode,
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}

export function useFundFlowSector(params: SectorListParams) {
  return useQuery({
    queryKey: ['fund-flow', 'sector', params],
    queryFn: () => fundFlowApi.sectorList(params).then((r) => r.data ?? []),
    ...SHARED_OPTIONS,
  });
}

export function useFundFlowEtf(params: EtfListParams) {
  return useQuery({
    queryKey: ['fund-flow', 'etf', params],
    queryFn: () => fundFlowApi.etfList(params).then((r) => r.data ?? []),
    ...SHARED_OPTIONS,
  });
}

export function useFundFlowSignals(params: SignalListParams) {
  return useQuery({
    queryKey: ['fund-flow', 'signals', params],
    queryFn: () => fundFlowApi.signalsList(params).then((r) => r.data ?? []),
    ...SHARED_OPTIONS,
  });
}

/**
 * Manual refresh helper: invalidate every fund-flow query key so callers
 * can wire the header "刷新" button without re-implementing the cache map.
 */
export function useRefreshFundFlow() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ['fund-flow'] });
}