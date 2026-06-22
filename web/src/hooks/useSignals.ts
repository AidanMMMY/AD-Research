import { useQuery } from '@tanstack/react-query';
import { signalApi } from '@/api/signal';

export function useSignals() {
  return useQuery({
    queryKey: ['signals-latest'],
    queryFn: async () => {
      const res = await signalApi.getLatest(50);
      return res.data;
    },
    staleTime: 60_000,
  });
}
