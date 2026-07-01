import client from './client';
import type { AttributionResponse } from '@/types/backtest';

export const analysisApi = {
  correlation: (codes: string[], window?: number, method?: 'pearson' | 'spearman') =>
    client.get<{ codes: string[]; matrix: number[][] }>('/analysis/correlation', {
      params: { codes, window, method },
    }),
  attribution: (id: number) =>
    client.get<AttributionResponse>(`/analysis/attribution/${id}`),
  /**
   * Rank ETFs by an indicator field (e.g. `return_1m`, `sharpe_1y`).
   * Backed by `GET /api/v1/analysis/ranking`.
   */
  ranking: (
    sortBy: string = 'sharpe_1y',
    order: 'asc' | 'desc' = 'desc',
    limit: number = 20,
  ) =>
    client.get<{ items: Array<Record<string, unknown>> }>('/analysis/ranking', {
      params: { sort_by: sortBy, order, limit },
    }),
};
