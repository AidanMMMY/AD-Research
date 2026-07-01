import { useMutation, useQueryClient } from '@tanstack/react-query';
import { strategyApi } from '@/api/strategy';
import type { StrategyRunRequest, StrategyRunResponse } from '@/types/strategy';

export function useRunStrategy() {
  const queryClient = useQueryClient();

  return useMutation<StrategyRunResponse, Error, StrategyRunRequest>({
    mutationFn: async (data: StrategyRunRequest) => {
      const res = await strategyApi.run(data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['signals-latest'] });
    },
  });
}
