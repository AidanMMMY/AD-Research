/**
 * News & Sentiment shared types (mirrors `web/src/api/news.ts`).
 *
 * These types are the single source of truth for any component that
 * consumes the news / sentiment endpoints. Keep them in sync with the
 * backend Pydantic schemas in `app/schemas/news*.py`.
 */

/** Market segment identifier.
 *
 *  ``global`` is a frontend-only sentinel introduced in M22-2 (2026-07-04)
 *  to represent "all markets combined" — it is mapped on the backend
 *  to a union of the concrete markets (``cn_a``, ``us``, ``crypto`` and
 *  any legacy bucket the collector has ever written).
 */
export type NewsMarket = 'cn_a' | 'us' | 'crypto' | 'global';

/** Sentiment label output by the LLM processor. */
export type SentimentLabel = 'negative' | 'neutral' | 'positive';

/** Importance bucket (1 = informational, 5 = market-moving). */
export type ImportanceLevel = 1 | 2 | 3 | 4 | 5;

/** A symbol mentioned by a news article. */
export interface NewsSymbol {
  symbol: string;
  market?: string | null;
  /** How the symbol was matched (e.g. ``ticker``, ``name``, ``alias``). */
  match_type?: string | null;
  /** Instrument display name (cached from ``etf_info``). */
  name?: string | null;
  /** Chinese display name (cached from ``etf_info``). */
  name_zh?: string | null;
}

/** Per-article engagement metrics (likes / shares / …). */
export interface NewsEngagement {
  likes?: number;
  comments?: number;
  shares?: number;
  views?: number;
  [key: string]: number | undefined;
}

/** A single news article surfaced by the news collector. */
export interface NewsArticle {
  id: number;
  /** Source identifier, e.g. ``xinhua``, ``xueqiu``, ``reddit``… */
  source: string;
  url: string;
  market: NewsMarket;
  language: string;
  title: string;
  body: string | null;
  author: string | null;
  published_at: string;
  fetched_at: string;
  engagement: NewsEngagement;
  /** Normalized score in ``[-1, 1]`` if processed by the LLM. */
  sentiment_score: number | null;
  sentiment_label: SentimentLabel | null;
  /** Confidence of the LLM sentiment call, in ``[0, 1]``. */
  sentiment_confidence: number | null;
  /** Optional list of driver phrases extracted by the LLM. */
  sentiment_drivers: string[] | null;
  event_category: string | null;
  importance: ImportanceLevel | null;
  symbols: NewsSymbol[];
  /** Lazily-fetched full body (Jina Reader cache). ``null`` when never loaded. */
  full_content: string | null;
  /** ISO timestamp of the last successful Jina fetch (cache TTL anchor). */
  full_content_fetched_at: string | null;
  /** Cached Chinese translation (DeepSeek). Populated only for English articles. */
  translated_zh: string | null;
  /** ISO timestamp of the last successful DeepSeek translation. */
  translation_generated_at: string | null;
}

/** Response shape for ``POST /news/{id}/fetch-content``. */
export interface NewsFetchContentResponse {
  success: boolean;
  /** Cached Markdown body, or a fallback to the intro on failure. */
  content: string | null;
  cached: boolean;
  error: string | null;
}

/** Response shape for ``POST /news/{id}/translate``. */
export interface NewsTranslateResponse {
  /** The Chinese translation (Markdown). May equal the cached value. */
  translation: string;
  /** True if we returned a previously-stored row (no LLM call). */
  cached: boolean;
  /** Tokens consumed by the LLM call; null on cache hit or no-usage response. */
  tokens_used: number | null;
  /** ISO timestamp of the translation (cache anchor). */
  generated_at: string | null;
  /** Source language code as stored on the article. */
  source_language: string;
  /** Target language code, e.g. ``zh``. */
  target_language: string;
}

/** Paginated list response. */
export interface NewsListResponse {
  items: NewsArticle[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** List query parameters. */
export interface NewsListParams {
  market?: NewsMarket | string;
  symbol?: string;
  source?: string;
  from_date?: string;
  to_date?: string;
  /** Full-text search query (best-effort, server-side). */
  q?: string;
  page?: number;
  page_size?: number;
  importance_min?: ImportanceLevel;
  /**
   * Filter by one or more ``event_category`` values. The backend
   * accepts a list (``?event_category=geopolitics&event_category=central_bank``)
   * — repeat the query parameter to OR multiple categories together.
   *
   * Allowed values mirror the LLM prompt in
   * ``app/services/news/sentiment/prompts.py``:
   * earnings|m&a|product|macro|regulation|guidance|analyst|legal|rumor
   * |geopolitics|central_bank|election|trade_war|sanction|other
   */
  event_category?: string[];
}

/** Watchlist-scoped metadata returned by /news/watchlist. */
export interface NewsWatchlistMeta {
  /** All favorite instrument codes the user has on file. */
  symbols: string[];
  /** How many of those symbols have at least one matching article. */
  symbols_with_news: number;
  /** Total matching articles across all pages. */
  total_articles: number;
}

/** Response shape for /news/watchlist — same as ``NewsListResponse``
 *  plus a ``watchlist`` metadata block. */
export interface NewsWatchlistResponse extends NewsListResponse {
  watchlist: NewsWatchlistMeta;
}

/** Query parameters for the watchlist-scoped list endpoint.
 *  Note: ``symbol`` is intentionally absent — the symbol set comes from
 *  the user's favorites on the server side. */
export interface NewsWatchlistParams {
  market?: NewsMarket | string;
  source?: string;
  from_date?: string;
  to_date?: string;
  page?: number;
  page_size?: number;
  event_category?: string[];
}

/** Per-source count summary returned by `/news/stats/sources`. */
export interface NewsSourceStat {
  source: string;
  total: number;
  last_7d: number;
  last_24h: number;
}

/** Last etl_log row for a single news source. */
export interface NewsSourceLatestEtl {
  status: string;
  records: number | null;
  error_msg: string | null;
  finished_at: string | null;
  started_at: string | null;
}

/** Per-source diagnostics row returned by /news/health. */
export interface NewsSourceHealth {
  source: string;
  job_id: string | null;
  total: number;
  last_24h: number;
  last_published_at: string | null;
  last_fetched_at: string | null;
  latest_etl: NewsSourceLatestEtl | null;
}

/** APScheduler job snapshot entry. */
export interface NewsSchedulerJob {
  id: string;
  name: string;
  next_run_time: string | null;
}

/** Full response shape of /news/health. */
export interface NewsHealthResponse {
  as_of: string;
  scheduler_running: boolean;
  scheduler_jobs: NewsSchedulerJob[];
  scheduler_total_jobs: number;
  sources: NewsSourceHealth[];
}

/** Theme weight in retail sentiment aggregation. */
export interface RetailTheme {
  theme: string;
  percentage: number;
}

/** Aggregated retail-sentiment output. */
export interface RetailSentiment {
  /** Overall sentiment score in ``[-1, 1]``. */
  overall: number;
  bull_bear_ratio: { bull: number; bear: number };
  main_themes: RetailTheme[];
  /** Controversy index, ``[0, 1]`` (higher = more disagreement). */
  controversy: number;
  /** LLM-generated summary of retail discussion. */
  summary: string;
}
