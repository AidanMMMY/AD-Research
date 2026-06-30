import { useQuery } from '@tanstack/react-query';
import { analysisApi } from '@/api/analysis';
import type { AttributionResponse } from '@/types/backtest';

export function useAttribution(backtestId: number | string) {
  return useQuery<AttributionResponse>({
    queryKey: ['backtest-attribution', backtestId],
    queryFn: async () => {
      const res = await analysisApi.attribution(Number(backtestId));
      return res.data;
    },
    enabled: !!backtestId,
  });
}
