import client from './client';
import type { Strategy, StrategyTemplate, StrategyCreate, StrategyUpdate, StrategyListResponse } from '@/types/strategy';

export const strategyApi = {
  list: () => client.get<StrategyListResponse>('/strategies'),
  getTemplates: () => client.get<StrategyTemplate[]>('/strategies/templates'),
  get: (id: number) => client.get<Strategy>(`/strategies/${id}`),
  create: (data: StrategyCreate) => client.post<Strategy>('/strategies', data),
  update: (id: number, data: StrategyUpdate) => client.put<Strategy>(`/strategies/${id}`, data),
  delete: (id: number) => client.delete(`/strategies/${id}`),
};
