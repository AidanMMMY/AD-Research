import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { liveTradingApi } from '@/api/liveTrading';
import type { LiveConfigCreate, LiveConfigUpdate, LiveOrderCreate } from '@/types/trading';

// ---------------------------------------------------------------------------
// Configs
// ---------------------------------------------------------------------------

export function useLiveConfigs() {
  return useQuery({
    queryKey: ['live-configs'],
    queryFn: async () => {
      const res = await liveTradingApi.listConfigs();
      return res.data;
    },
    staleTime: 30_000,
  });
}

export function useCreateConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: LiveConfigCreate) => liveTradingApi.createConfig(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['live-configs'] });
    },
  });
}

export function useUpdateConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: LiveConfigUpdate }) =>
      liveTradingApi.updateConfig(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['live-configs'] });
    },
  });
}

export function useDeleteConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => liveTradingApi.deleteConfig(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['live-configs'] });
    },
  });
}

// ---------------------------------------------------------------------------
// Read-only
// ---------------------------------------------------------------------------

export function useLiveAccount(configId: number | undefined) {
  return useQuery({
    queryKey: ['live-account', configId],
    queryFn: async () => {
      const res = await liveTradingApi.getAccount(configId!);
      return res.data;
    },
    enabled: !!configId,
    staleTime: 30_000,
  });
}

export function useLivePositions(configId: number | undefined) {
  return useQuery({
    queryKey: ['live-positions', configId],
    queryFn: async () => {
      const res = await liveTradingApi.listPositions(configId!);
      return res.data;
    },
    enabled: !!configId,
    staleTime: 15_000,
  });
}

export function useLiveOrders(configId: number | undefined, limit = 50) {
  return useQuery({
    queryKey: ['live-orders', configId, limit],
    queryFn: async () => {
      const res = await liveTradingApi.listOrders(configId!, limit);
      return res.data;
    },
    enabled: !!configId,
    staleTime: 10_000,
  });
}

// ---------------------------------------------------------------------------
// Write
// ---------------------------------------------------------------------------

export function usePlaceLiveOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      configId,
      data,
    }: {
      configId: number;
      data: LiveOrderCreate;
    }) => liveTradingApi.placeOrder(configId, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['live-orders', variables.configId] });
      queryClient.invalidateQueries({ queryKey: ['live-positions', variables.configId] });
      queryClient.invalidateQueries({ queryKey: ['live-account', variables.configId] });
      queryClient.invalidateQueries({ queryKey: ['risk-status', variables.configId] });
    },
  });
}

export function useCancelLiveOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ configId, orderId }: { configId: number; orderId: number }) =>
      liveTradingApi.cancelOrder(configId, orderId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['live-orders', variables.configId] });
    },
  });
}

// ---------------------------------------------------------------------------
// Risk
// ---------------------------------------------------------------------------

export function useRiskStatus(configId: number | undefined) {
  return useQuery({
    queryKey: ['risk-status', configId],
    queryFn: async () => {
      const res = await liveTradingApi.getRiskStatus(configId!);
      return res.data;
    },
    enabled: !!configId,
    staleTime: 10_000,
    refetchInterval: 30_000, // auto-refresh
  });
}

export function useResetCircuitBreaker() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (configId: number) =>
      liveTradingApi.resetCircuitBreaker(configId),
    onSuccess: (_data, configId) => {
      queryClient.invalidateQueries({ queryKey: ['risk-status', configId] });
    },
  });
}

export function useRiskRules() {
  return useQuery({
    queryKey: ['risk-rules'],
    queryFn: async () => {
      const res = await liveTradingApi.listRiskRules();
      return res.data;
    },
    staleTime: 60_000,
  });
}
