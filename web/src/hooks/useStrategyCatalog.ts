import { useQuery } from '@tanstack/react-query';
import { strategyApi } from '@/api/strategy';
import type { StrategyCatalogItem } from '@/types/strategy';

export function useStrategyCatalog(family?: string) {
  return useQuery<StrategyCatalogItem[]>({
    queryKey: ['strategy-catalog', family],
    queryFn: async () => {
      const res = await strategyApi.getCatalog(family);
      return res.data;
    },
    staleTime: 300_000,
  });
}
