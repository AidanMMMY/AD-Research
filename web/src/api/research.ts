import client from './client';

export interface ResearchNote {
  id: number;
  instrument_code: string;
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
  avg_score: number;
  label: string;
  positive_count: number;
  negative_count: number;
  neutral_count: number;
  total_articles: number;
  period_days: number;
}

export const researchApi = {
  generateNote: (instrument_code: string) =>
    client.post<ResearchNote>('/research/notes/generate', { instrument_code }),

  getNotes: (instrument_code: string, note_type?: string, limit = 20) =>
    client.get<ResearchNote[]>(`/research/notes/${instrument_code}`, {
      params: { note_type, limit },
    }),

  getSentiment: (instrument_code: string, days = 7) =>
    client.get<SentimentAggregate | null>(`/research/sentiment/${instrument_code}`, {
      params: { days },
    }),

  ingestSentiment: (instrument_code: string, days = 3) =>
    client.post(`/research/sentiment/${instrument_code}/ingest`, null, {
      params: { days },
    }),
};
