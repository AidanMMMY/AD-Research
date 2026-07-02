import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import client from './client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SearchTrend {
  id: number;
  keyword: string;
  region: string;
  source: string;
  trade_date: string;
  value: number;
  is_partial: boolean;
  proxy_quality: string;
  category?: string | null;
  fetched_at?: string | null;
  created_at?: string | null;
}

export interface SearchTrendListParams {
  page?: number;
  page_size?: number;
  source?: string;
  region?: string;
  category?: string;
  keyword?: string;
  start_date?: string;
  end_date?: string;
  sort_by?: string;
  sort_dir?: 'asc' | 'desc';
}

export interface SearchTrendListResponse {
  items: SearchTrend[];
  total: number;
  page: number;
  page_size: number;
}

export interface SearchTrendDashboard {
  as_of?: string | null;
  baidu: {
    trade_date?: string;
    count?: number;
    top_keywords?: SearchTrend[];
  };
  google: {
    trade_date?: string;
    count?: number;
    top_keywords?: SearchTrend[];
  };
}

export interface SearchTrendCompareResponse {
  keyword: string;
  series: SearchTrend[];
}

// ---------------------------------------------------------------------------
// API + hooks
// ---------------------------------------------------------------------------

function buildQueryString(params: SearchTrendListParams | undefined): string {
  if (!params) return '';
  const parts: string[] = [];
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
  }
  return parts.length === 0 ? '' : `?${parts.join('&')}`;
}

export const searchTrendsApi = {
  list: (params?: SearchTrendListParams) =>
    client.get<SearchTrendListResponse>(`/search-trends${buildQueryString(params)}`),
  dashboard: () => client.get<SearchTrendDashboard>('/search-trends/dashboard'),
  compare: (keyword: string, days: number = 30) =>
    client.get<SearchTrendCompareResponse>(
      `/search-trends/compare?keyword=${encodeURIComponent(keyword)}&days=${days}`,
    ),
  refresh: () =>
    client.post<{ status: string; records: string; warnings: string[] }>(
      '/search-trends/refresh',
    ),
};

export function useSearchTrendList(params?: SearchTrendListParams) {
  return useQuery({
    queryKey: ['search-trends', 'list', params],
    queryFn: async () => (await searchTrendsApi.list(params)).data,
    staleTime: 60_000,
  });
}

export function useSearchTrendDashboard() {
  return useQuery({
    queryKey: ['search-trends', 'dashboard'],
    queryFn: async () => (await searchTrendsApi.dashboard()).data,
    staleTime: 60_000,
  });
}

export function useSearchTrendCompare(keyword: string | null, days: number = 30) {
  return useQuery({
    queryKey: ['search-trends', 'compare', keyword, days],
    queryFn: async () => {
      if (!keyword) return null;
      const res = await searchTrendsApi.compare(keyword, days);
      return res.data;
    },
    enabled: !!keyword,
    staleTime: 120_000,
  });
}

export function useRefreshSearchTrends() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => (await searchTrendsApi.refresh()).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['search-trends'] });
    },
  });
}