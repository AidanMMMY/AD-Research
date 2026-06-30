import client from './client';
import type {
  NewsArticle,
  NewsListParams,
  NewsListResponse,
  NewsSourceStat,
  RetailSentiment,
} from '@/types/news';

export type {
  NewsArticle,
  NewsEngagement,
  NewsListParams,
  NewsListResponse,
  NewsMarket,
  NewsSourceStat,
  NewsSymbol,
  RetailSentiment,
  RetailTheme,
  SentimentLabel,
  ImportanceLevel,
} from '@/types/news';

/**
 * News & retail-sentiment API client.
 *
 * Endpoints are owned by Agent B's backend module. The frontend
 * intentionally only types the request/response shape; if the backend
 * changes, update the shared `types/news.ts` instead of this file.
 */
export const newsApi = {
  /** Paginated article list with filtering. */
  list(params: NewsListParams = {}): Promise<{ data: NewsListResponse }> {
    return client.get<NewsListResponse>('/news', { params });
  },

  /** Fetch a single article by id (full body, all symbols). */
  get(id: number): Promise<{ data: NewsArticle }> {
    return client.get<NewsArticle>(`/news/${id}`);
  },

  /** Per-source aggregate counts (for the source filter chip strip). */
  sourceStats(): Promise<{ data: NewsSourceStat[] }> {
    return client.get<NewsSourceStat[]>('/news/sources/stats');
  },

  /**
   * Aggregated retail-discussion sentiment for a single symbol.
   *
   * The backend is expected to fan this out across social sources
   * (xueqiu / reddit / …) and produce:
   * - an overall normalized score in ``[-1, 1]``;
   * - bull/bear ratio;
   * - a list of main themes with percentage weight;
   * - a controversy index;
   * - an LLM summary.
   *
   * Until Agent E lands the social-aggregation pipeline, this endpoint
   * may return 404 — callers should treat that as "no data" rather
   * than a hard error.
   */
  retailSentiment(symbol: string, window = '7d'): Promise<{ data: RetailSentiment }> {
    return client.get<RetailSentiment>(`/news/retail-sentiment/${encodeURIComponent(symbol)}`, {
      params: { window },
    });
  },
};
