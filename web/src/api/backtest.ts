import client from './client';
import type { Backtest, BacktestCreate, BacktestListResponse } from '@/types/backtest';

export const backtestApi = {
  list: (params?: { strategy_id?: number; limit?: number }) =>
    client.get<BacktestListResponse>('/backtests', { params }),
  get: (id: number) => client.get<Backtest>(`/backtests/${id}`),
  create: (data: BacktestCreate) => client.post<Backtest>('/backtests', data),
};
