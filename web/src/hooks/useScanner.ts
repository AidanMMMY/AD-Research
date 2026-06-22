import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { scannerApi } from '@/api/scanner';

export function useScanner() {
  const queryClient = useQueryClient();

  const logsQuery = useQuery({
    queryKey: ['etf-scan-logs'],
    queryFn: async () => {
      const res = await scannerApi.getLogs(50);
      return res.data;
    },
    staleTime: 60_000,
  });

  const scanMutation = useMutation({
    mutationFn: () => scannerApi.triggerScan(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['etf-scan-logs'] }),
  });

  return {
    logs: logsQuery.data || [],
    isLoading: logsQuery.isLoading,
    scan: scanMutation.mutateAsync,
    isScanning: scanMutation.isPending,
  };
}
