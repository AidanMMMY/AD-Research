import { useQuery } from '@tanstack/react-query';
import { sectorRotationApi } from '@/api/sectorRotation';
import type { SectorClassification } from '@/types/sector_rotation';

export function useSectorRotation(
  trade_date?: string,
  window_weeks?: number,
  classification: SectorClassification = 'GICS',
) {
  return useQuery({
    queryKey: ['sector-rotation', trade_date, window_weeks, classification],
    queryFn: () =>
      sectorRotationApi
        .analyze(trade_date, window_weeks, classification)
        .then((r) => r.data),
    staleTime: 60_000,
  });
}

export function useSectorList(classification: SectorClassification = 'GICS') {
  return useQuery({
    queryKey: ['sector-list', classification],
    queryFn: () => sectorRotationApi.sectors(classification).then((r) => r.data),
    staleTime: 5 * 60_000,
  });
}

/**
 * Top-N constituents for a single sector (STOCK + ETF).
 *
 * Disabled when ``sector`` is empty so the underlying query doesn't
 * fire before the user picks a row.
 */
export function useSectorConstituents(
  sector: string | null | undefined,
  top_n = 20,
  trade_date?: string,
  classification: SectorClassification = 'GICS',
) {
  return useQuery({
    queryKey: ['sector-constituents', sector, top_n, trade_date, classification],
    queryFn: () =>
      sectorRotationApi
        .constituents(sector as string, { top_n, trade_date, classification })
        .then((r) => r.data),
    enabled: Boolean(sector),
    staleTime: 60_000,
  });
}
