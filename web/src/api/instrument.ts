import client from './client';
import type {
  InstrumentListResponse,
  InstrumentInfo,
  InstrumentFilterParams,
  ETFHoldingResponse,
  ETFHoldingSnapshotsResponse,
} from '@/types/instrument';

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
  categories: (params?: InstrumentFilterParams) =>
    client.get<{ categories: string[] }>('/etfs/categories/list', { params }),
  markets: () => client.get<{ markets: string[] }>('/etfs/markets/list'),
  sparkline: (code: string, days = 30) =>
    client.get<SparklineResponse>(`/etfs/${code}/sparkline`, { params: { days } }),
  sectors: (params?: InstrumentFilterParams) =>
    client.get<{ sectors: string[] }>('/etfs/sectors/list', { params }),
  industries: (params?: InstrumentFilterParams) =>
    client.get<{ industries: string[] }>('/etfs/industries/list', { params }),
  subCategories: (params?: InstrumentFilterParams) =>
    client.get<{ sub_categories: string[] }>('/etfs/sub-categories/list', { params }),
  managers: (params?: InstrumentFilterParams) =>
    client.get<{ managers: string[] }>('/etfs/managers/list', { params }),
  currencies: (params?: InstrumentFilterParams) =>
    client.get<{ currencies: string[] }>('/etfs/currencies/list', { params }),
  countries: (params?: InstrumentFilterParams) =>
    client.get<{ countries: string[] }>('/etfs/countries/list', { params }),
  underlyingIndices: (params?: InstrumentFilterParams) =>
    client.get<{ underlying_indices: string[] }>('/etfs/underlying-indices/list', { params }),
  listingMarkets: (params?: InstrumentFilterParams) =>
    client.get<{ listing_markets: string[] }>('/etfs/listing-markets/list', { params }),
  boards: (params?: InstrumentFilterParams) =>
    client.get<{ boards: string[] }>('/etfs/boards/list', { params }),
  holdings: (code: string, params?: { date?: string }) =>
    client.get<ETFHoldingResponse>(`/etfs/${code}/holdings`, { params }),
  holdingsSnapshots: (code: string) =>
    client.get<ETFHoldingSnapshotsResponse>(`/etfs/${code}/holdings/snapshots`),
};
