import client from './client';
import type {
  CryptoListResponse,
  CryptoDetail,
  DailyBar,
  IndicatorSummary,
  IndicatorHistory,
  CryptoScore,
  CryptoSignal,
  ResearchNote,
  CryptoFilterParams,
} from '@/types/crypto';

export const cryptoApi = {
  /** List crypto instruments with optional filtering. Enriched with live price. */
  list: (params?: CryptoFilterParams) =>
    client.get<CryptoListResponse>('/crypto', { params }).then((r) => r.data),

  /** Full detail for a single cryptocurrency. */
  get: (code: string) =>
    client.get<CryptoDetail>(`/crypto/${code}`).then((r) => r.data),

  /** Historical OHLCV bars. */
  history: (
    code: string,
    params?: { start_date?: string; end_date?: string; limit?: number },
  ) =>
    client
      .get<DailyBar[]>(`/crypto/${code}/history`, { params })
      .then((r) => r.data),

  /** Latest technical indicators. */
  indicators: (code: string) =>
    client.get<IndicatorSummary>(`/crypto/${code}/indicators`).then((r) => r.data),

  /** Historical technical indicators. */
  indicatorHistory: (
    code: string,
    params?: { start?: string; end?: string; limit?: number },
  ) =>
    client
      .get<IndicatorHistory>(`/crypto/${code}/indicators/history`, { params })
      .then((r) => r.data),

  /** Latest composite score. */
  score: (code: string) =>
    client.get<CryptoScore>(`/crypto/${code}/score`).then((r) => r.data),

  /** Recent trading signals. */
  signals: (code: string, limit = 20) =>
    client
      .get<CryptoSignal[]>(`/crypto/${code}/signals`, { params: { limit } })
      .then((r) => r.data),

  /** Recent AI research notes. */
  research: (code: string, limit = 5) =>
    client
      .get<ResearchNote[]>(`/crypto/${code}/research`, { params: { limit } })
      .then((r) => r.data),

  /** Available markets (always ["CRYPTO"] for now). */
  markets: () =>
    client.get<{ markets: string[] }>('/crypto/markets/list').then((r) => r.data),
};
