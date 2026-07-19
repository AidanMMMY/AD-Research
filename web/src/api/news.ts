import client from './client';
import type {
  EventSignalsParams,
  EventSignalsResponse,
  NewsArticle,
  NewsFetchContentResponse,
  NewsHealthResponse,
  NewsListParams,
  NewsListResponse,
  NewsSourceStat,
  NewsTranslateResponse,
  NewsWatchlistParams,
  NewsWatchlistResponse,
  RetailSentiment,
} from '@/types/news';

export type {
  EventSignal,
  EventSignalsParams,
  EventSignalsResponse,
  NewsArticle,
  NewsEngagement,
  NewsFetchContentResponse,
  NewsHealthResponse,
  NewsListParams,
  NewsListResponse,
  NewsMarket,
  NewsSourceStat,
  NewsSymbol,
  NewsTranslateResponse,
  NewsWatchlistMeta,
  NewsWatchlistParams,
  NewsWatchlistResponse,
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
    // Axios serializes arrays as ``?event_category=a&event_category=b``
    // by default, which is exactly what the FastAPI backend expects for
    // a repeatable query parameter. No transform needed.
    return client.get<NewsListResponse>('/news', { params });
  },

  /**
   * Event-driven signals derived from classified news articles.
   * Returns a flat list of signals with direction, importance and
   * affected symbols. The backend is expected to classify articles by
   * event category and derive a bullish / bearish / neutral stance.
   */
  eventSignals(params: EventSignalsParams = {}): Promise<{ data: EventSignalsResponse }> {
    return client.get<EventSignalsResponse>('/news/event-signals', { params });
  },

  /**
   * Paginated article list scoped to the current user's favorites.
   *
   * Returns the same shape as ``list()`` plus a ``watchlist`` block
   * with the symbol set, coverage count, and total articles — used by
   * the UI to render "自选标的 X 个 · 相关资讯 Y 条".
   */
  watchlist(params: NewsWatchlistParams = {}): Promise<{ data: NewsWatchlistResponse }> {
    return client.get<NewsWatchlistResponse>('/news/watchlist', { params });
  },

  /** Fetch a single article by id (full body, all symbols). */
  get(id: number): Promise<{ data: NewsArticle }> {
    return client.get<NewsArticle>(`/news/${id}`);
  },

  /** Per-source aggregate counts (for the source filter chip strip). */
  sourceStats(): Promise<{ data: { sources: NewsSourceStat[] } }> {
    return client.get<{ sources: NewsSourceStat[] }>('/news/stats/sources');
  },

  /** Per-source diagnostics + APScheduler status. */
  health(): Promise<{ data: NewsHealthResponse }> {
    return client.get<NewsHealthResponse>('/news/health');
  },

  /**
   * Trigger a Jina Reader fetch for the given article. Returns the
   * cached Markdown body when the server already has a fresh copy.
   * Rejection/non-2xx is rare — the endpoint never raises 5xx because
   * Jina errors are coerced into ``{success:false, error:'...'}``.
   */
  fetchContent(id: number): Promise<{ data: NewsFetchContentResponse }> {
    return client.post<NewsFetchContentResponse>(`/news/${id}/fetch-content`);
  },

  /**
   * Translate an English article's body to Chinese via DeepSeek.
   *
   * The server caches the result on the article row, so the second
   * call for the same id returns ``cached=true`` with no LLM cost.
   * Backend enforces ``language == 'en'`` (400 otherwise) and a
   * per-user daily rate limit (429 otherwise).
   */
  translate(id: number, targetLanguage = 'zh'): Promise<{ data: NewsTranslateResponse }> {
    return client.post<NewsTranslateResponse>(
      `/news/${id}/translate`,
      undefined,
      { params: { target_language: targetLanguage } },
    );
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
