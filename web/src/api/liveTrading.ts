import client from './client';
import type {
  LiveAccount,
  LiveConfig,
  LiveConfigCreate,
  LiveConfigUpdate,
  LiveOrder,
  LiveOrderCreate,
  LivePosition,
  RiskRule,
  RiskStatus,
} from '@/types/trading';

const BASE = '/live-trading';

export const liveTradingApi = {
  // --- Configs ---
  listConfigs: () => client.get<LiveConfig[]>(`${BASE}/configs`),
  createConfig: (data: LiveConfigCreate) =>
    client.post<LiveConfig>(`${BASE}/configs`, data),
  updateConfig: (id: number, data: LiveConfigUpdate) =>
    client.put<LiveConfig>(`${BASE}/configs/${id}`, data),
  deleteConfig: (id: number) => client.delete(`${BASE}/configs/${id}`),

  // --- Read-only ---
  getAccount: (configId: number) =>
    client.get<LiveAccount>(`${BASE}/configs/${configId}/account`),
  listPositions: (configId: number) =>
    client.get<LivePosition[]>(`${BASE}/configs/${configId}/positions`),
  listOrders: (configId: number, limit = 50) =>
    client.get<LiveOrder[]>(`${BASE}/configs/${configId}/orders`, {
      params: { limit },
    }),
  listTrades: (configId: number, symbol?: string, limit = 50) =>
    client.get(`${BASE}/configs/${configId}/trades`, {
      params: { symbol, limit },
    }),

  // --- Write ---
  placeOrder: (configId: number, data: LiveOrderCreate) =>
    client.post<LiveOrder>(`${BASE}/configs/${configId}/orders`, data),
  cancelOrder: (configId: number, orderId: number) =>
    client.delete(`${BASE}/configs/${configId}/orders/${orderId}`),

  // --- Risk ---
  getRiskStatus: (configId: number) =>
    client.get<RiskStatus>(`${BASE}/configs/${configId}/risk-status`),
  resetCircuitBreaker: (configId: number) =>
    client.post(`${BASE}/configs/${configId}/circuit-breaker/reset`),
  listRiskRules: () => client.get<RiskRule[]>(`${BASE}/risk-rules`),
};
