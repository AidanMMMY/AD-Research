import client from './client';
import type { InstrumentListResponse, InstrumentInfo, InstrumentFilterParams } from '@/types/instrument';

export interface SparklineResponse {
  code: string;
  days: number;
  points: number[];
  dates: string[];
}

export const instrumentApi = {
  list: (params?: InstrumentFilterParams) =>
    client.get<InstrumentListResponse>('/etfs', { params }),
  get: (code: string) => client.get<InstrumentInfo>(`/etfs/${code}`),
  categories: (params?: { market?: string; instrument_type?: string }) =>
    client.get<{ categories: string[] }>('/etfs/categories/list', { params }),
  markets: () => client.get<{ markets: string[] }>('/etfs/markets/list'),
  sparkline: (code: string, days = 30) =>
    client.get<SparklineResponse>(`/etfs/${code}/sparkline`, { params: { days } }),
};
