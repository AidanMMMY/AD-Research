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

export function useInstrumentCategories(filters?: InstrumentFilterParams) {
  const params = filters
    ? { market: filters.market, instrument_type: filters.instrument_type }
    : undefined;
  return useQuery({
    queryKey: ['instrument-categories', params],
    queryFn: () => instrumentApi.categories(params).then((r) => r.data.categories),
    staleTime: 300_000,
  });
}

export function useInstrumentSectors(filters?: InstrumentFilterParams) {
  const params = filters
    ? { market: filters.market, instrument_type: filters.instrument_type }
    : undefined;
  return useQuery({
    queryKey: ['instrument-sectors', params],
    queryFn: () => instrumentApi.sectors(params).then((r) => r.data.sectors),
    staleTime: 300_000,
  });
}

export function useInstrumentIndustries(filters?: InstrumentFilterParams) {
  const params = filters
    ? { market: filters.market, instrument_type: filters.instrument_type }
    : undefined;
  return useQuery({
    queryKey: ['instrument-industries', params],
    queryFn: () => instrumentApi.industries(params).then((r) => r.data.industries),
    staleTime: 300_000,
  });
}

export function useInstrumentSubCategories(filters?: InstrumentFilterParams) {
  const params = filters
    ? { market: filters.market, instrument_type: filters.instrument_type }
    : undefined;
  return useQuery({
    queryKey: ['instrument-sub-categories', params],
    queryFn: () => instrumentApi.subCategories(params).then((r) => r.data.sub_categories),
    staleTime: 300_000,
  });
}

export function useInstrumentManagers(filters?: InstrumentFilterParams) {
  const params = filters
    ? { market: filters.market, instrument_type: filters.instrument_type }
    : undefined;
  return useQuery({
    queryKey: ['instrument-managers', params],
    queryFn: () => instrumentApi.managers(params).then((r) => r.data.managers),
    staleTime: 300_000,
  });
}

export function useInstrumentCurrencies(filters?: InstrumentFilterParams) {
  const params = filters
    ? { market: filters.market, instrument_type: filters.instrument_type }
    : undefined;
  return useQuery({
    queryKey: ['instrument-currencies', params],
    queryFn: () => instrumentApi.currencies(params).then((r) => r.data.currencies),
    staleTime: 300_000,
  });
}

export function useInstrumentCountries(filters?: InstrumentFilterParams) {
  const params = filters
    ? { market: filters.market, instrument_type: filters.instrument_type }
    : undefined;
  return useQuery({
    queryKey: ['instrument-countries', params],
    queryFn: () => instrumentApi.countries(params).then((r) => r.data.countries),
    staleTime: 300_000,
  });
}

export function useInstrumentUnderlyingIndices(filters?: InstrumentFilterParams) {
  const params = filters
    ? { market: filters.market, instrument_type: filters.instrument_type }
    : undefined;
  return useQuery({
    queryKey: ['instrument-underlying-indices', params],
    queryFn: () => instrumentApi.underlyingIndices(params).then((r) => r.data.underlying_indices),
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
