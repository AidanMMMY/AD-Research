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
  sectors: (params?: { market?: string; instrument_type?: string }) =>
    client.get<{ sectors: string[] }>('/etfs/sectors/list', { params }),
  industries: (params?: { market?: string; instrument_type?: string }) =>
    client.get<{ industries: string[] }>('/etfs/industries/list', { params }),
  subCategories: (params?: { market?: string; instrument_type?: string }) =>
    client.get<{ sub_categories: string[] }>('/etfs/sub-categories/list', { params }),
  managers: (params?: { market?: string; instrument_type?: string }) =>
    client.get<{ managers: string[] }>('/etfs/managers/list', { params }),
  currencies: (params?: { market?: string; instrument_type?: string }) =>
    client.get<{ currencies: string[] }>('/etfs/currencies/list', { params }),
  countries: (params?: { market?: string; instrument_type?: string }) =>
    client.get<{ countries: string[] }>('/etfs/countries/list', { params }),
  underlyingIndices: (params?: { market?: string; instrument_type?: string }) =>
    client.get<{ underlying_indices: string[] }>('/etfs/underlying-indices/list', { params }),
};
