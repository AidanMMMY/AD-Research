import client from './client';
import type { NewsArticle } from '@/types/news';

/**
 * Learning-center ("学习中心") API client (2026-08-02).
 *
 * The backend joins ``news_article`` against the source-metadata
 * mapping (content_type + topic) and returns list items shaped exactly
 * like ``/news`` rows, plus two extra fields. Sorting is done
 * server-side (importance first, then recency) — the frontend must NOT
 * re-sort.
 */

/** Knowledge-topic taxonomy (source-level mapping, see analysis doc §2.3). */
export type LearningTopic =
  | 'allocation'
  | 'valuation'
  | 'macro'
  | 'industry'
  | 'psychology'
  | 'tools'
  | 'research';

/** Coarse content nature assigned per source. */
export type LearningContentType = 'flash' | 'deep' | 'edu';

/** A feed item: the ``/news`` list row plus learning metadata. */
export interface LearningArticle extends NewsArticle {
  content_type: LearningContentType;
  topic: LearningTopic | string;
}

export interface LearningFeedParams {
  topic?: LearningTopic | string;
  content_type?: LearningContentType;
  page?: number;
  page_size?: number;
  /** Lookback window in days (server default 90). */
  days?: number;
}

export interface LearningFeedResponse {
  items: LearningArticle[];
  total: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
}

export interface LearningTopicStat {
  topic: LearningTopic | string;
  count: number;
}

export interface LearningTopicsResponse {
  topics: LearningTopicStat[];
}

/** Chinese labels for the topic taxonomy (single source of truth for the UI). */
export const LEARNING_TOPIC_LABELS: Record<string, string> = {
  allocation: '资产配置',
  valuation: '估值方法',
  macro: '宏观入门',
  industry: '行业研究',
  psychology: '交易心理',
  tools: '工具教程',
  research: '深度研究',
};

/** Canonical display order for the topic chip strip. */
export const LEARNING_TOPIC_ORDER: LearningTopic[] = [
  'allocation',
  'valuation',
  'macro',
  'industry',
  'psychology',
  'tools',
  'research',
];

export const learningApi = {
  /** Paginated knowledge feed, importance-first ordering (server-side). */
  feed(params: LearningFeedParams = {}): Promise<{ data: LearningFeedResponse }> {
    return client.get<LearningFeedResponse>('/learning/feed', { params });
  },

  /** Per-topic article counts for the chip strip. */
  topics(): Promise<{ data: LearningTopicsResponse }> {
    return client.get<LearningTopicsResponse>('/learning/topics');
  },
};
