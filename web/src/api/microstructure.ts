import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import client from './client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface LhbRecord {
  id: number;
  trade_date: string;
  ts_code: string;
  name: string;
  close?: number | null;
  pct_change?: number | null;
  turnover_rate?: number | null;
  amount?: number | null;
  lhb_buy_amount?: number | null;
  lhb_sell_amount?: number | null;
  lhb_net_amount?: number | null;
  total_buy?: number | null;
  total_sell?: number | null;
  total_net?: number | null;
  net_buy_amt?: number | null;
  buy_seat_count?: number | null;
  sell_seat_count?: number | null;
  reason: string;
  source: string;
  created_at?: string | null;
}

export interface LhbListResponse {
  items: LhbRecord[];
  total: number;
  page: number;
  page_size: number;
}

export interface HsgtFlow {
  id: number;
  trade_date: string;
  type: string;
  buy_amount?: number | null;
  sell_amount?: number | null;
  net_amount?: number | null;
  balance?: number | null;
  source: string;
  created_at?: string | null;
}

export interface HsgtListResponse {
  items: HsgtFlow[];
  total: number;
}

export interface MarginBalance {
  id: number;
  trade_date: string;
  ts_code: string;
  name: string;
  financing_balance?: number | null;
  financing_buy?: number | null;
  securities_balance?: number | null;
  securities_sell?: number | null;
  exchange: string;
  source: string;
  created_at?: string | null;
}

export interface MarginListResponse {
  items: MarginBalance[];
  total: number;
  page: number;
  page_size: number;
}

export interface RestrictedRelease {
  id: number;
  ts_code: string;
  name: string;
  restricted_date: string;
  restricted_type: string;
  restricted_number?: number | null;
  restricted_amount?: number | null;
  lift_ratio?: number | null;
  source: string;
  created_at?: string | null;
}

export interface RestrictedListResponse {
  items: RestrictedRelease[];
  total: number;
  page: number;
  page_size: number;
}

export interface MicrostructureSummary {
  as_of?: string | null;
  lhb: {
    trade_date?: string | null;
    count?: number;
    top_buyers?: LhbRecord[];
    top_sellers?: LhbRecord[];
  };
  hsgt: {
    trade_date?: string | null;
    north_net?: number | null;
    sh_net?: number | null;
    sz_net?: number | null;
    rows?: HsgtFlow[];
  };
  margin: {
    trade_date?: string | null;
    total_financing_balance?: number;
    total_securities_balance?: number;
  };
  release: {
    upcoming_30d_count?: number;
    upcoming_30d_amount?: number;
  };
}

// ---------------------------------------------------------------------------
// API + hooks
// ---------------------------------------------------------------------------

function buildQueryString(params: Record<string, unknown> | undefined): string {
  if (!params) return '';
  const parts: string[] = [];
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
  }
  return parts.length === 0 ? '' : `?${parts.join('&')}`;
}

export const microstructureApi = {
  listLhb: (params: Record<string, unknown> = {}) =>
    client.get<LhbListResponse>(`/microstructure/lhb${buildQueryString(params)}`),
  listHsgt: (params: Record<string, unknown> = {}) =>
    client.get<HsgtListResponse>(`/microstructure/hsgt${buildQueryString(params)}`),
  listMargin: (params: Record<string, unknown> = {}) =>
    client.get<MarginListResponse>(`/microstructure/margin${buildQueryString(params)}`),
  listReleases: (params: Record<string, unknown> = {}) =>
    client.get<RestrictedListResponse>(
      `/microstructure/restricted-releases${buildQueryString(params)}`,
    ),
  summary: () => client.get<MicrostructureSummary>('/microstructure/summary'),
  facets: () => client.get<{ exchanges: string[] }>('/microstructure/facets'),
  refresh: () =>
    client.post<{ status: string; records: string; warnings: string[] }>(
      '/microstructure/refresh',
    ),
};

export function useMicrostructureLhb(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: ['microstructure', 'lhb', params],
    queryFn: async () => (await microstructureApi.listLhb(params)).data,
    staleTime: 60_000,
  });
}

export function useMicrostructureHsgt(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: ['microstructure', 'hsgt', params],
    queryFn: async () => (await microstructureApi.listHsgt(params)).data,
    staleTime: 60_000,
  });
}

export function useMicrostructureMargin(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: ['microstructure', 'margin', params],
    queryFn: async () => (await microstructureApi.listMargin(params)).data,
    staleTime: 60_000,
  });
}

export function useMicrostructureReleases(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: ['microstructure', 'releases', params],
    queryFn: async () => (await microstructureApi.listReleases(params)).data,
    staleTime: 120_000,
  });
}

export function useMicrostructureSummary() {
  return useQuery({
    queryKey: ['microstructure', 'summary'],
    queryFn: async () => (await microstructureApi.summary()).data,
    staleTime: 60_000,
  });
}

export function useRefreshMicrostructure() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => (await microstructureApi.refresh()).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['microstructure'] });
    },
  });
}