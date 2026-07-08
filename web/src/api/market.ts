import client from './client';
import type { OHLCV, MarketSnapshot, IndicatorData } from '@/types/instrument';

export const marketApi = {
  history: (code: string, params?: { start_date?: string; end_date?: string; limit?: number; adjusted?: boolean }) =>
    client.get<{ items: OHLCV[] }>(`/market-data/${code}/history`, { params }),
  snapshot: (codes: string[]) => client.get<MarketSnapshot[]>('/market-data/snapshot', { params: { codes } }),
  indicators: (code: string) => client.get<IndicatorData>(`/indicators/${code}`),
  indicatorsHistory: (code: string, params?: { start_date?: string; end_date?: string }) =>
    client.get<{ items: IndicatorData[] }>(`/indicators/${code}/history`, { params }),
};
