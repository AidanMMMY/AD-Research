import client from './client';
import type {
  Strategy,
  StrategyCatalogItem,
  StrategyCreate,
  StrategyListResponse,
  StrategyRunRequest,
  StrategyRunResponse,
  StrategyTemplate,
  StrategyUpdate,
} from '@/types/strategy';

export const strategyApi = {
  list: () => client.get<StrategyListResponse>('/strategies'),
  getTemplates: () => client.get<StrategyTemplate[]>('/strategies/templates'),
  getCatalog: (family?: string) =>
    client.get<StrategyCatalogItem[]>(family ? `/strategies/catalog/${family}` : '/strategies/catalog'),
  run: (data: StrategyRunRequest) => client.post<StrategyRunResponse>('/strategies/run', data),
  get: (id: number) => client.get<Strategy>(`/strategies/${id}`),
  create: (data: StrategyCreate) => client.post<Strategy>('/strategies', data),
  update: (id: number, data: StrategyUpdate) => client.put<Strategy>(`/strategies/${id}`, data),
  delete: (id: number) => client.delete(`/strategies/${id}`),
};
