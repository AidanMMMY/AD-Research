import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { backtestApi } from '@/api/backtest';
import type { BacktestCreate } from '@/types/backtest';
import { useApiErrorToast } from './useApiError';

export function useBacktests(strategyId?: number) {
  const queryClient = useQueryClient();

  const backtestsQuery = useQuery({
    queryKey: ['backtests', strategyId],
    queryFn: async () => {
      const res = await backtestApi.list({ strategy_id: strategyId });
      return res.data;
    },
    staleTime: 30_000,
  });

  useApiErrorToast(
    `backtests:${strategyId ?? 'all'}`,
    backtestsQuery.error,
    '加载回测列表失败',
  );

  const createMutation = useMutation({
    mutationFn: (data: BacktestCreate) => backtestApi.create(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['backtests'], exact: false }),
  });

  return {
    backtests: backtestsQuery.data?.items || [],
    isLoading: backtestsQuery.isLoading,
    create: createMutation.mutateAsync,
  };
}

export function useBacktestDetail(id: number | string) {
  const query = useQuery({
    queryKey: ['backtest', id],
    queryFn: async () => {
      const res = await backtestApi.get(Number(id));
      return res.data;
    },
    enabled: !!id,
  });

  useApiErrorToast(
    `backtest:${id}`,
    query.error,
    '加载回测详情失败',
  );

  return query;
}
