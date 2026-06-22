import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { backtestApi } from '@/api/backtest';
import type { BacktestCreate } from '@/types/backtest';

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
  return useQuery({
    queryKey: ['backtest', id],
    queryFn: async () => {
      const res = await backtestApi.get(Number(id));
      return res.data;
    },
    enabled: !!id,
  });
}
