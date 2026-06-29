import { useQuery } from '@tanstack/react-query';
import { etfApi } from '@/api';
import type { ETFFilterParams } from '@/types/etf';

export function useETFList(params?: ETFFilterParams) {
  return useQuery({
    queryKey: ['etfs', params],
    queryFn: () => etfApi.list(params).then((r) => r.data),
    staleTime: 60_000,
  });
}

export function useETFDetail(code: string) {
  return useQuery({
    queryKey: ['etf', code],
    queryFn: () => etfApi.get(code).then((r) => r.data),
    enabled: !!code,
  });
}

export function useETFCategories(filters?: { market?: string; instrument_type?: string }) {
  return useQuery({
    queryKey: ['etf-categories', filters],
    queryFn: () => etfApi.categories(filters).then((r) => r.data.categories),
    staleTime: 300_000,
  });
}

export function useETFMarkets() {
  return useQuery({
    queryKey: ['etf-markets'],
    queryFn: () => etfApi.markets().then((r) => r.data.markets),
    staleTime: 300_000,
  });
}
