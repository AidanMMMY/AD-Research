import client from './client';
import type { NewsMarket, SentimentAggregateItem } from '@/types/news';

export interface AIStatus {
  available: boolean;
  provider: string;
  model: string;
  setup_url: string;
  monthly_cost_estimate: string;
}

export interface ResearchNote {
  id: number;
  instrument_code: string;
  name?: string | null;
  name_zh?: string | null;
  note_type: string;
  content: string;
  summary?: string;
  sentiment?: string;
  confidence?: number;
  generated_at?: string;
  created_at?: string;
}

export interface SentimentAggregate {
  instrument_code: string;
  name?: string | null;
  name_zh?: string | null;
  avg_score: number;
  label: string;
  positive_count: number;
  negative_count: number;
  neutral_count: number;
  total_articles: number;
  period_days: number;
}

export const researchApi = {
  getAIStatus: () =>
    client.get<AIStatus>('/research/ai/status'),

  generateNote: (instrument_code: string) =>
    client.post<ResearchNote>('/research/notes/generate', { instrument_code }),

  getMyNotes: (note_type?: string, limit = 50) =>
    client.get<ResearchNote[]>('/research/notes', {
      params: { note_type, limit },
    }),

  getNotes: (instrument_code: string, note_type?: string, limit = 20) =>
    client.get<ResearchNote[]>(`/research/notes/${instrument_code}`, {
      params: { note_type, limit },
    }),

  deleteNote: (id: number) =>
    client.delete(`/research/notes/${id}`),

  getSentiment: (instrument_code: string, days = 7) =>
    client.get<SentimentAggregate | null>(`/research/sentiment/${instrument_code}`, {
      params: { days },
    }),

  ingestSentiment: (instrument_code: string, days = 3) =>
    client.post(`/research/sentiment/${instrument_code}/ingest`, null, {
      params: { days },
    }),

  sentimentAggregate: (params?: {
    market?: NewsMarket | 'all';
    days?: number;
    limit?: number;
    min_articles?: number;
  }) =>
    client
      .get<{ items: SentimentAggregateItem[] }>('/research/sentiment-data/aggregate', { params })
      .then((resp) => ({ data: resp.data.items })),
};
