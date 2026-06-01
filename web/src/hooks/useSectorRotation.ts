import { useQuery } from '@tanstack/react-query';
import { sectorRotationApi } from '@/api/sectorRotation';

export function useSectorRotation(trade_date?: string, window_weeks?: number) {
  return useQuery({
    queryKey: ['sector-rotation', trade_date, window_weeks],
    queryFn: () => sectorRotationApi.analyze(trade_date, window_weeks).then((r) => r.data),
    staleTime: 60_000,
  });
}

export function useSectorList() {
  return useQuery({
    queryKey: ['sector-list'],
    queryFn: () => sectorRotationApi.sectors().then((r) => r.data),
    staleTime: 5 * 60_000,
  });
}
