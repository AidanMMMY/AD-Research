import client from './client';
import type { InstrumentInfo, InstrumentListResponse } from '@/types/instrument';

export interface StockFilterParams {
  market?: string;
  category?: string;
  industry?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

export interface SparklineResponse {
  code: string;
  days: number;
  points: number[];
  dates: string[];
}

/**
 * A-share (and other market) individual-stock API client.
 *
 * The backend (app/api/v1/stocks.py) reuses the ETF list/detail endpoints
 * with `instrument_type=STOCK` filter; the response shape is identical
 * (ETFInfoResponse). Sparkline is exposed via the ETF endpoint
 * (/etfs/{code}/sparkline) which reads from instrument_daily_bar and
 * works for all instruments.
 */
export const stocksApi = {
  list: (params?: StockFilterParams) =>
    client.get<InstrumentListResponse>('/stocks', { params }),
  get: (code: string) => client.get<InstrumentInfo>(`/stocks/${code}`),
  sparkline: (code: string, days = 30) =>
    client.get<SparklineResponse>(`/etfs/${code}/sparkline`, { params: { days } }),
};
