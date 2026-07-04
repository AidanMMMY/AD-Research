import { useQuery } from '@tanstack/react-query';
import { signalApi } from '@/api/signal';
import { useApiErrorToast } from './useApiError';

export function useSignals() {
  const query = useQuery({
    queryKey: ['signals-latest'],
    queryFn: async () => {
      const res = await signalApi.getLatest(50);
      return res.data;
    },
    staleTime: 60_000,
  });

  useApiErrorToast(
    'signals-latest',
    query.error,
    '加载最新信号失败',
  );

  return query;
}
