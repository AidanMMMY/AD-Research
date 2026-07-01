import { useQuery } from '@tanstack/react-query';
import { instrumentApi } from '@/api';
import type { InstrumentFilterParams } from '@/types/instrument';

export function useInstrumentList(params?: InstrumentFilterParams) {
  return useQuery({
    queryKey: ['instruments', params],
    queryFn: () => instrumentApi.list(params).then((r) => r.data),
    staleTime: 60_000,
  });
}

export function useInstrumentDetail(code: string) {
  return useQuery({
    queryKey: ['instrument', code],
    queryFn: () => instrumentApi.get(code).then((r) => r.data),
    enabled: !!code,
  });
}

export function useInstrumentCategories(filters?: { market?: string; instrument_type?: string }) {
  return useQuery({
    queryKey: ['instrument-categories', filters],
    queryFn: () => instrumentApi.categories(filters).then((r) => r.data.categories),
    staleTime: 300_000,
  });
}

export function useInstrumentMarkets() {
  return useQuery({
    queryKey: ['instrument-markets'],
    queryFn: () => instrumentApi.markets().then((r) => r.data.markets),
    staleTime: 300_000,
  });
}
