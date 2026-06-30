import client from './client';
import type { ETFListResponse, ETFInfo, ETFFilterParams } from '@/types/etf';

export interface SparklineResponse {
  code: string;
  days: number;
  points: number[];
  dates: string[];
}

export const etfApi = {
  list: (params?: ETFFilterParams) =>
    client.get<ETFListResponse>('/etfs', { params }),
  get: (code: string) => client.get<ETFInfo>(`/etfs/${code}`),
  categories: (params?: { market?: string; instrument_type?: string }) =>
    client.get<{ categories: string[] }>('/etfs/categories/list', { params }),
  markets: () => client.get<{ markets: string[] }>('/etfs/markets/list'),
  sparkline: (code: string, days = 30) =>
    client.get<SparklineResponse>(`/etfs/${code}/sparkline`, { params: { days } }),
};
