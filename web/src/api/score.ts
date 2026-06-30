import client from './client';
import type {
  ETFScoreListResponse,
  ETFScore,
  ScoreTemplate,
  ScoreTemplateCreate,
  ScoreTemplateUpdate,
} from '@/types/score';

export const scoreApi = {
  list: (params?: { template_id?: number; market?: string; category?: string; trade_date?: string; limit?: number }) =>
    client.get<ETFScoreListResponse>('/scores', { params }),
  get: (code: string, params?: { template_id?: number; trade_date?: string }) =>
    client.get<ETFScore>(`/scores/${code}`, { params }),

  // Template management
  listTemplates: () => client.get<ScoreTemplate[]>('/scores/templates'),
  createTemplate: (data: ScoreTemplateCreate) =>
    client.post<ScoreTemplate>('/scores/templates', data),
  updateTemplate: (id: number, data: ScoreTemplateUpdate) =>
    client.put<ScoreTemplate>(`/scores/templates/${id}`, data),
  deleteTemplate: (id: number) => client.delete<void>(`/scores/templates/${id}`),

  // Legacy alias (kept for back-compat with existing call sites)
  templates: () => client.get<ScoreTemplate[]>('/scores/templates'),
};
