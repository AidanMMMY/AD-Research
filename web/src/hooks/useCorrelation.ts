import { useQuery } from '@tanstack/react-query';
import { analysisApi } from '@/api/analysis';

export function useCorrelation(codes: string[], window?: number, method?: 'pearson' | 'spearman') {
  return useQuery({
    queryKey: ['correlation', codes, window, method],
    queryFn: () => analysisApi.correlation(codes, window, method).then((r) => r.data),
    enabled: codes.length >= 2,
    staleTime: 60_000,
  });
}
