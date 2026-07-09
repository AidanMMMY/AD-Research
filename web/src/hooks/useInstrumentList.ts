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
  return useQuery({
    queryKey: ['instrument-categories', filters],
    queryFn: () => instrumentApi.categories(filters).then((r) => r.data.categories),
    staleTime: 300_000,
  });
}

export function useInstrumentSectors(filters?: InstrumentFilterParams) {
  return useQuery({
    queryKey: ['instrument-sectors', filters],
    queryFn: () => instrumentApi.sectors(filters).then((r) => r.data.sectors),
    staleTime: 300_000,
  });
}

export function useInstrumentIndustries(filters?: InstrumentFilterParams) {
  return useQuery({
    queryKey: ['instrument-industries', filters],
    queryFn: () => instrumentApi.industries(filters).then((r) => r.data.industries),
    staleTime: 300_000,
  });
}

export function useInstrumentSubCategories(filters?: InstrumentFilterParams) {
  return useQuery({
    queryKey: ['instrument-sub-categories', filters],
    queryFn: () => instrumentApi.subCategories(filters).then((r) => r.data.sub_categories),
    staleTime: 300_000,
  });
}

export function useInstrumentManagers(filters?: InstrumentFilterParams) {
  return useQuery({
    queryKey: ['instrument-managers', filters],
    queryFn: () => instrumentApi.managers(filters).then((r) => r.data.managers),
    staleTime: 300_000,
  });
}

export function useInstrumentCurrencies(filters?: InstrumentFilterParams) {
  return useQuery({
    queryKey: ['instrument-currencies', filters],
    queryFn: () => instrumentApi.currencies(filters).then((r) => r.data.currencies),
    staleTime: 300_000,
  });
}

export function useInstrumentCountries(filters?: InstrumentFilterParams) {
  return useQuery({
    queryKey: ['instrument-countries', filters],
    queryFn: () => instrumentApi.countries(filters).then((r) => r.data.countries),
    staleTime: 300_000,
  });
}

export function useInstrumentUnderlyingIndices(filters?: InstrumentFilterParams) {
  return useQuery({
    queryKey: ['instrument-underlying-indices', filters],
    queryFn: () => instrumentApi.underlyingIndices(filters).then((r) => r.data.underlying_indices),
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

export function useInstrumentListingMarkets(filters?: InstrumentFilterParams) {
  return useQuery({
    queryKey: ['instrument-listing-markets', filters],
    queryFn: () =>
      instrumentApi.listingMarkets(filters).then((r) => r.data.listing_markets),
    staleTime: 300_000,
  });
}

export function useInstrumentBoards(filters?: InstrumentFilterParams) {
  return useQuery({
    queryKey: ['instrument-boards', filters],
    queryFn: () => instrumentApi.boards(filters).then((r) => r.data.boards),
    staleTime: 300_000,
  });
}
