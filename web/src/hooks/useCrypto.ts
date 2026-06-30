import { useQuery } from '@tanstack/react-query';
import { cryptoApi } from '@/api/crypto';
import type { CryptoFilterParams } from '@/types/crypto';

/** Paginated crypto list with optional filters. */
export function useCryptoList(params?: CryptoFilterParams) {
  return useQuery({
    queryKey: ['crypto-list', params],
    queryFn: async () => cryptoApi.list(params),
    staleTime: 30_000,
  });
}

/** Full detail (basic info + live price + latest indicator). */
export function useCryptoDetail(code: string) {
  return useQuery({
    queryKey: ['crypto-detail', code],
    queryFn: async () => cryptoApi.get(code),
    enabled: !!code,
    staleTime: 30_000,
  });
}

/** Historical OHLCV bars. */
export function useCryptoHistory(
  code: string,
  params?: { start_date?: string; end_date?: string; limit?: number },
) {
  return useQuery({
    queryKey: ['crypto-history', code, params],
    queryFn: async () => cryptoApi.history(code, params),
    enabled: !!code,
    staleTime: 120_000,
  });
}

/** Latest technical indicators. */
export function useCryptoIndicators(code: string) {
  return useQuery({
    queryKey: ['crypto-indicators', code],
    queryFn: async () => cryptoApi.indicators(code),
    enabled: !!code,
  });
}

/** Latest composite score. */
export function useCryptoScore(code: string) {
  return useQuery({
    queryKey: ['crypto-score', code],
    queryFn: async () => cryptoApi.score(code),
    enabled: !!code,
  });
}

/** Recent signals. */
export function useCryptoSignals(code: string, limit = 20) {
  return useQuery({
    queryKey: ['crypto-signals', code, limit],
    queryFn: async () => cryptoApi.signals(code, limit),
    enabled: !!code,
  });
}

/** AI research notes. */
export function useCryptoResearch(code: string, limit = 5) {
  return useQuery({
    queryKey: ['crypto-research', code, limit],
    queryFn: async () => cryptoApi.research(code, limit),
    enabled: !!code,
  });
}
