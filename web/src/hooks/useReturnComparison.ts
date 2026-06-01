import { useQuery } from '@tanstack/react-query';
import { marketApi } from '@/api/market';

export function useReturnComparison(codes: string[], limit?: number) {
  return useQuery({
    queryKey: ['return-comparison', codes, limit],
    queryFn: async () => {
      const results = await Promise.all(
        codes.map((code) =>
          marketApi.history(code, { limit }).then((r) => ({
            code,
            items: r.data.items,
          }))
        )
      );
      return results;
    },
    enabled: codes.length >= 1,
    staleTime: 60_000,
  });
}
