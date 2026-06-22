import client from './client';
import type { SignalListResponse, SignalGenerateRequest, SignalGenerateResponse } from '@/types/signal';

export const signalApi = {
  list: (params?: { strategy_id?: number; etf_code?: string; trade_date?: string; limit?: number }) =>
    client.get<SignalListResponse>('/signals', { params }),
  getLatest: (limit?: number) =>
    client.get<SignalListResponse>('/signals/latest', { params: { limit } }),
  generate: (data: SignalGenerateRequest) =>
    client.post<SignalGenerateResponse>('/signals/generate', data),
};
