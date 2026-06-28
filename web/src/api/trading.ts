import client from './client';
import type {
  PaperAccount,
  PaperAccountCreate,
  PaperAccountListResponse,
  PaperOrder,
  PaperOrderCreate,
  PaperOrderListResponse,
  PaperPosition,
  PnLSummary,
} from '@/types/trading';

const BASE = '/paper-trading';

export const paperTradingApi = {
  // --- Accounts ---
  listAccounts: () => client.get<PaperAccountListResponse>(`${BASE}/accounts`),
  createAccount: (data: PaperAccountCreate) =>
    client.post<PaperAccount>(`${BASE}/accounts`, data),
  getAccount: (id: number) => client.get<PaperAccount>(`${BASE}/accounts/${id}`),
  deleteAccount: (id: number) => client.delete(`${BASE}/accounts/${id}`),

  // --- Orders ---
  listOrders: (accountId: number, limit = 50) =>
    client.get<PaperOrderListResponse>(`${BASE}/accounts/${accountId}/orders`, {
      params: { limit },
    }),
  placeOrder: (accountId: number, data: PaperOrderCreate) =>
    client.post<PaperOrder>(`${BASE}/accounts/${accountId}/orders`, data),
  cancelOrder: (accountId: number, orderId: number) =>
    client.delete(`${BASE}/accounts/${accountId}/orders/${orderId}`),

  // --- Positions ---
  listPositions: (accountId: number) =>
    client.get<PaperPosition[]>(`${BASE}/accounts/${accountId}/positions`),

  // --- PnL ---
  getPnL: (accountId: number) =>
    client.get<PnLSummary>(`${BASE}/accounts/${accountId}/pnl`),

  // --- Actions ---
  syncMarketValues: (accountId: number) =>
    client.post<{ updated: number }>(`${BASE}/accounts/${accountId}/sync`),
  autoTrade: (accountId: number, tradeDate?: string) =>
    client.post<PaperOrder[]>(`${BASE}/accounts/${accountId}/auto-trade`, null, {
      params: tradeDate ? { trade_date: tradeDate } : undefined,
    }),
};
