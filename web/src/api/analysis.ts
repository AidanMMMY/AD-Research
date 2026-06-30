import client from './client';
import type { AttributionResponse } from '@/types/backtest';

export const analysisApi = {
  correlation: (codes: string[], window?: number, method?: 'pearson' | 'spearman') =>
    client.get<{ codes: string[]; matrix: number[][] }>('/analysis/correlation', {
      params: { codes, window, method },
    }),
  attribution: (id: number) =>
    client.get<AttributionResponse>(`/analysis/attribution/${id}`),
};
