import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { paperTradingApi } from '@/api/trading';
import type { PaperAccountCreate, PaperOrderCreate } from '@/types/trading';

// ---------------------------------------------------------------------------
// Accounts
// ---------------------------------------------------------------------------

export function usePaperAccounts() {
  return useQuery({
    queryKey: ['paper-accounts'],
    queryFn: async () => {
      const res = await paperTradingApi.listAccounts();
      return res.data;
    },
    staleTime: 15_000,
  });
}

export function usePaperAccount(accountId: number | undefined) {
  return useQuery({
    queryKey: ['paper-account', accountId],
    queryFn: async () => {
      const res = await paperTradingApi.getAccount(accountId!);
      return res.data;
    },
    enabled: !!accountId,
    staleTime: 15_000,
  });
}

export function useCreateAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: PaperAccountCreate) => paperTradingApi.createAccount(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['paper-accounts'] });
    },
  });
}

export function useDeleteAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (accountId: number) => paperTradingApi.deleteAccount(accountId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['paper-accounts'] });
    },
  });
}

// ---------------------------------------------------------------------------
// Orders
// ---------------------------------------------------------------------------

export function usePaperOrders(accountId: number | undefined, limit = 50) {
  return useQuery({
    queryKey: ['paper-orders', accountId, limit],
    queryFn: async () => {
      const res = await paperTradingApi.listOrders(accountId!, limit);
      return res.data;
    },
    enabled: !!accountId,
    staleTime: 10_000,
  });
}

export function usePlaceOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      accountId,
      data,
    }: {
      accountId: number;
      data: PaperOrderCreate;
    }) => paperTradingApi.placeOrder(accountId, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['paper-orders', variables.accountId] });
      queryClient.invalidateQueries({ queryKey: ['paper-positions', variables.accountId] });
      queryClient.invalidateQueries({ queryKey: ['paper-account', variables.accountId] });
      queryClient.invalidateQueries({ queryKey: ['paper-pnl', variables.accountId] });
    },
  });
}

// ---------------------------------------------------------------------------
// Positions
// ---------------------------------------------------------------------------

export function usePaperPositions(accountId: number | undefined) {
  return useQuery({
    queryKey: ['paper-positions', accountId],
    queryFn: async () => {
      const res = await paperTradingApi.listPositions(accountId!);
      return res.data;
    },
    enabled: !!accountId,
    staleTime: 10_000,
  });
}

// ---------------------------------------------------------------------------
// PnL
// ---------------------------------------------------------------------------

export function usePaperPnL(accountId: number | undefined) {
  return useQuery({
    queryKey: ['paper-pnl', accountId],
    queryFn: async () => {
      const res = await paperTradingApi.getPnL(accountId!);
      return res.data;
    },
    enabled: !!accountId,
    staleTime: 15_000,
  });
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

export function useSyncMarketValues() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (accountId: number) => paperTradingApi.syncMarketValues(accountId),
    onSuccess: (_data, accountId) => {
      queryClient.invalidateQueries({ queryKey: ['paper-positions', accountId] });
      queryClient.invalidateQueries({ queryKey: ['paper-pnl', accountId] });
      queryClient.invalidateQueries({ queryKey: ['paper-account', accountId] });
    },
  });
}

export function useAutoTrade() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      accountId,
      tradeDate,
    }: {
      accountId: number;
      tradeDate?: string;
    }) => paperTradingApi.autoTrade(accountId, tradeDate),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['paper-orders', variables.accountId] });
      queryClient.invalidateQueries({ queryKey: ['paper-positions', variables.accountId] });
      queryClient.invalidateQueries({ queryKey: ['paper-pnl', variables.accountId] });
      queryClient.invalidateQueries({ queryKey: ['paper-account', variables.accountId] });
    },
  });
}
