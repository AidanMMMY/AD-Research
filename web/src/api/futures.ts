import { useQuery } from '@tanstack/react-query';
import client from './client';

export interface FuturesContractOut {
  code: string;
  name: string;
  exchange: string;
  exchange_label: string | null;
  product: string;
  underlying_instrument: string | null;
  contract_size: string | null;
  price_unit: string | null;
  quote_unit: string | null;
  is_main: boolean;
  list_date: string | null;
  delist_date: string | null;
  last_seen_at: string | null;
}

export interface FuturesContractListResponse {
  items: FuturesContractOut[];
  total: number;
  page: number;
  page_size: number;
}

export interface FuturesDashboardSection {
  product: string;
  product_label: string | null;
  items: FuturesDailyBarOut[];
  best_performer: FuturesDailyBarOut | null;
  worst_performer: FuturesDailyBarOut | null;
  count: number;
}

export interface FuturesDashboardResponse {
  sections: FuturesDashboardSection[];
  trade_date: string | null;
  total_contracts: number;
}

export interface FuturesDailyBarOut {
  code: string;
  trade_date: string;
  open: string | null;
  high: string | null;
  low: string | null;
  close: string | null;
  settle: string | null;
  pre_settle: string | null;
  volume: number | null;
  open_interest: number | null;
  turnover: string | null;
  warehouse_receipts: number | null;
  settle_change_pct: number | null;
  change_pct: number | null;
}

export interface FuturesLeaderboardRow {
  code: string;
  name: string;
  exchange: string;
  product: string;
  close: string | null;
  settle: string | null;
  pre_settle: string | null;
  change_pct: number | null;
  volume: number | null;
  open_interest: number | null;
  turnover: string | null;
}

export interface FuturesLeaderboardResponse {
  items: FuturesLeaderboardRow[];
  direction: 'gainers' | 'losers';
  exchange: string | null;
  trade_date: string | null;
}

export interface FuturesStats {
  total_contracts: number;
  total_bars: number;
  latest_trade_date: string | null;
}

const BASE = '/futures';

export const futuresApi = {
  contracts: (params?: { exchange?: string; product?: string; is_main?: boolean; search?: string; page?: number; page_size?: number }) => {
    const parts: string[] = [];
    const append = (k: string, v: unknown) => {
      if (v === undefined || v === null || v === '') return;
      parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
    };
    append('exchange', params?.exchange);
    append('product', params?.product);
    if (params?.is_main !== undefined) append('is_main', params.is_main);
    append('search', params?.search);
    append('page', params?.page ?? 1);
    append('page_size', params?.page_size ?? 200);
    const qs = parts.length === 0 ? '' : `?${parts.join('&')}`;
    return client.get<FuturesContractListResponse>(`${BASE}/contracts${qs}`);
  },
  dashboard: () => client.get<FuturesDashboardResponse>(`${BASE}/dashboard`),
  leaderboard: (direction: 'gainers' | 'losers', exchange?: string, top = 30) => {
    const parts = [`direction=${direction}`, `top=${top}`];
    if (exchange) parts.push(`exchange=${encodeURIComponent(exchange)}`);
    return client.get<FuturesLeaderboardResponse>(`${BASE}/leaderboard?${parts.join('&')}`);
  },
  stats: () => client.get<FuturesStats>(`${BASE}/stats`),
};

export function useFuturesDashboard() {
  return useQuery({
    queryKey: ['futures', 'dashboard'],
    queryFn: async () => {
      const res = await futuresApi.dashboard();
      return res.data;
    },
    staleTime: 60_000,
  });
}

export function useFuturesLeaderboard(direction: 'gainers' | 'losers', exchange?: string) {
  return useQuery({
    queryKey: ['futures', 'leaderboard', direction, exchange ?? null],
    queryFn: async () => {
      const res = await futuresApi.leaderboard(direction, exchange);
      return res.data;
    },
    staleTime: 60_000,
  });
}

export function useFuturesStats() {
  return useQuery({
    queryKey: ['futures', 'stats'],
    queryFn: async () => {
      const res = await futuresApi.stats();
      return res.data;
    },
    staleTime: 60_000,
  });
}