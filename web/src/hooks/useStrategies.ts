import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { strategyApi } from '@/api/strategy';
import type { StrategyCreate } from '@/types/strategy';

export function useStrategies() {
  const queryClient = useQueryClient();

  const strategiesQuery = useQuery({
    queryKey: ['strategies'],
    queryFn: async () => {
      const res = await strategyApi.list();
      return res.data;
    },
    staleTime: 30_000,
  });

  const templatesQuery = useQuery({
    queryKey: ['strategy-templates'],
    queryFn: async () => {
      const res = await strategyApi.getTemplates();
      return res.data;
    },
    staleTime: 300_000,
  });

  const createMutation = useMutation({
    mutationFn: (data: StrategyCreate) => strategyApi.create(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['strategies'] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => strategyApi.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['strategies'] }),
  });

  return {
    strategies: strategiesQuery.data?.items || [],
    templates: templatesQuery.data || [],
    isLoading: strategiesQuery.isLoading,
    create: createMutation.mutateAsync,
    delete: deleteMutation.mutateAsync,
  };
}
