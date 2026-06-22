import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { notificationApi } from '@/api/notification';
import type { NotificationConfigCreate } from '@/types/notification';

export function useNotifications() {
  const queryClient = useQueryClient();

  const configsQuery = useQuery({
    queryKey: ['notification-configs'],
    queryFn: async () => {
      const res = await notificationApi.listConfigs();
      return res.data;
    },
    staleTime: 30_000,
  });

  const createMutation = useMutation({
    mutationFn: (data: NotificationConfigCreate) => notificationApi.createConfig(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notification-configs'] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => notificationApi.deleteConfig(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notification-configs'] }),
  });

  const testMutation = useMutation({
    mutationFn: (id: number) => notificationApi.testConfig(id),
  });

  return {
    configs: configsQuery.data || [],
    isLoading: configsQuery.isLoading,
    create: createMutation.mutateAsync,
    delete: deleteMutation.mutateAsync,
    test: testMutation.mutateAsync,
  };
}
