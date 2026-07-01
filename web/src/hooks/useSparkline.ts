import { useQuery } from '@tanstack/react-query';
import { instrumentApi } from '@/api/instrument';

interface SparklineParams {
  code: string | null | undefined;
  days?: number;
  enabled?: boolean;
}

const DEFAULT_DAYS = 30;
/**
 * Fetch the recent close-price series for a single instrument.
 *
 * Returns the latest series in chronological order. Used for row-level
 * sparkline previews in list pages (ETFList, SectorRotation, ScoreRanking).
 */
export function useSparkline({ code, days = DEFAULT_DAYS, enabled }: SparklineParams) {
  return useQuery({
    queryKey: ['sparkline', code, days],
    queryFn: () => instrumentApi.sparkline(code as string, days).then((r) => r.data),
    enabled: enabled ?? !!code,
    staleTime: 5 * 60_000,
    // Don't refetch on window focus — sparklines are coarse-grained.
    refetchOnWindowFocus: false,
    retry: 1,
  });
}
