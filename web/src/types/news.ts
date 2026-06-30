/**
 * News & Sentiment shared types (mirrors `web/src/api/news.ts`).
 *
 * These types are the single source of truth for any component that
 * consumes the news / sentiment endpoints. Keep them in sync with the
 * backend Pydantic schemas in `app/schemas/news*.py`.
 */

/** Market segment identifier. */
export type NewsMarket = 'cn_a' | 'us' | 'crypto';

/** Sentiment label output by the LLM processor. */
export type SentimentLabel = 'negative' | 'neutral' | 'positive';

/** Importance bucket (1 = informational, 5 = market-moving). */
export type ImportanceLevel = 1 | 2 | 3 | 4 | 5;

/** A symbol mentioned by a news article. */
export interface NewsSymbol {
  symbol: string;
  market: string;
  /** How the symbol was matched (e.g. ``ticker``, ``name``, ``alias``). */
  match_type: string;
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
}

/** Paginated list response. */
export interface NewsListResponse {
  items: NewsArticle[];
  total: number;
  page: number;
  page_size: number;
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
}

/** Per-source count summary. */
export interface NewsSourceStat {
  source: string;
  count: number;
  last_24h: number;
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
