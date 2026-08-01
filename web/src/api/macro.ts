import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import client from './client';
import type {
  MacroCodeListResponse,
  MacroIndicatorDetail,
  MacroIndicatorListResponse,
  MacroLatestItem,
  MacroLatestResponse,
  MacroListParams,
  MacroRefreshResult,
} from '@/types/macro';
import { rangeToStartDate } from '@/utils/macroDetail';

export type { MacroLatestItem };

export interface MacroIndicatorItem {
  code: string;
  region: string;
  name_zh: string;
  name_en?: string | null;
  unit: string;
  source: string;
  period?: string | null;
  value?: number | null;
  fetched_at?: string | null;
}

export interface MacroIndicatorSeries {
  code: string;
  region: string;
  name_zh: string;
  name_en?: string | null;
  unit: string;
  source: string;
  points: { period: string; value: number }[];
}

function buildQueryString(params: MacroListParams | undefined): string {
  if (!params) return '';
  const parts: string[] = [];
  const append = (key: string, value: unknown) => {
    if (value === undefined || value === null || value === '') return;
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
  };
  append('region', params.region);
  append('code', params.code);
  append('start_period', params.start_period);
  append('end_period', params.end_period);
  append('page', params.page);
  append('page_size', params.page_size);
  return parts.length === 0 ? '' : `?${parts.join('&')}`;
}

export const macroApi = {
  /** List indicators + their latest value (FRED for region=us). */
  listIndicators(region?: string): Promise<{ data: MacroIndicatorItem[] }> {
    return client.get('/macro/indicators', { params: { region } });
  },

  /** Time series for one indicator. */
  getSeries(
    code: string,
    opts: { start_date?: string; end_date?: string; limit?: number } = {},
  ): Promise<{ data: MacroIndicatorSeries }> {
    return client.get(`/macro/indicators/${encodeURIComponent(code)}`, { params: opts });
  },

  /** Paginated observations across all sources (Phase 2 surface). */
  listObservations(
    params?: MacroListParams,
  ): Promise<{ data: MacroIndicatorListResponse }> {
    return client.get(`/macro/indicators-list${buildQueryString(params)}`);
  },

  /** Latest snapshot per (code, region) — used by the dashboard widgets. */
  latest(region?: string): Promise<{ data: MacroLatestResponse }> {
    return client.get('/macro/latest', { params: { region } });
  },

  /** Distinct codes for filter dropdowns. */
  codes(region?: string): Promise<{ data: MacroCodeListResponse }> {
    return client.get('/macro/codes', { params: { region } });
  },

  /** Manually trigger the China macro refresh job. */
  refreshChina(): Promise<{ data: MacroRefreshResult }> {
    return client.post('/macro/refresh-china');
  },

  /** Realtime snapshot of global indices (yfinance + akshare). */
  getGlobalIndicesRealtime(): Promise<{ data: { items: any[]; count: number } }> {
    return client.get('/macro/indices/global');
  },

  /** Manually trigger the global indices refresh job. */
  refreshGlobalIndices(): Promise<{ data: MacroRefreshResult }> {
    return client.post('/macro/refresh-global-indices');
  },

  /**
   * 全球速览指数详情（/global/:code 页面）。
   * GET /macro/indicators/{code}/detail —— 契约见 types/macro.ts 的
   * MacroIndicatorDetail；404 表示该 code 完全无数据。
   */
  getIndicatorDetail(
    code: string,
    params: { start_date?: string; end_date?: string; limit?: number } = {},
  ): Promise<{ data: MacroIndicatorDetail }> {
    return client.get(`/macro/indicators/${encodeURIComponent(code)}/detail`, { params });
  },
};

export function useMacroList(params?: MacroListParams) {
  return useQuery({
    queryKey: ['macro', 'list', params],
    queryFn: async () => {
      const res = await macroApi.listObservations(params);
      return res.data;
    },
    staleTime: 60_000,
  });
}

export function useMacroLatest(region?: string) {
  return useQuery({
    queryKey: ['macro', 'latest', region],
    queryFn: async () => {
      const res = await macroApi.latest(region);
      return res.data;
    },
    staleTime: 60_000,
  });
}

/**
 * 全球速览指数详情查询（/global/:code）。
 *
 * `range` 是详情页时间范围 key（'1M' | '3M' | '6M' | '1Y' | '3Y' | '5Y' | 'ALL'），
 * 内部经 rangeToStartDate 换算为 start_date；'ALL' 不传起点。
 */
export function useMacroIndicatorDetail(code: string | undefined, range: string) {
  return useQuery({
    queryKey: ['macro', 'detail', code, range],
    queryFn: async () => {
      const res = await macroApi.getIndicatorDetail(code as string, {
        start_date: rangeToStartDate(range),
        limit: 1500,
      });
      return res.data;
    },
    staleTime: 60_000,
    enabled: !!code,
    retry: 1,
  });
}

export function useMacroCodes(region?: string) {
  return useQuery({
    queryKey: ['macro', 'codes', region],
    queryFn: async () => {
      const res = await macroApi.codes(region);
      return res.data;
    },
    staleTime: 300_000,
  });
}

export function useRefreshChinaMacro() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const res = await macroApi.refreshChina();
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['macro'] });
    },
  });
}