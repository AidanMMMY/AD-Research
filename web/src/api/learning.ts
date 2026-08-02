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

/** 源级默认难度（P2, 2026-08-02）；null = 混合/不确定。 */
export type LearningDifficulty = 'beginner' | 'advanced';

/** A feed item: the ``/news`` list row plus learning metadata. */
export interface LearningArticle extends NewsArticle {
  content_type: LearningContentType | null;
  topic: LearningTopic | string | null;
}

export interface LearningFeedParams {
  topic?: LearningTopic | string;
  content_type?: LearningContentType;
  /** 难度筛选（P2）：beginner=入门 / advanced=进阶；不传=全部。 */
  difficulty?: LearningDifficulty;
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

/** ``POST /learning/articles/{id}/bookmark`` 响应。 */
export interface LearningBookmarkToggleResponse {
  article_id: number;
  /** 调用后的真实收藏状态（幂等语义在状态而非调用次数上）。 */
  bookmarked: boolean;
  bookmarked_at: string | null;
}

/** ``POST /learning/articles/{id}/read`` 响应。 */
export interface LearningReadResponse {
  article_id: number;
  read: boolean;
  /** 首次已读时间戳（重复标记不刷新）。 */
  read_at: string | null;
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

  /**
   * 收藏切换（P1, 2026-08-02）：未收藏→收藏，已收藏→取消。
   * 响应的 ``bookmarked`` 是调用后的真实状态（幂等语义在状态上）。
   */
  toggleBookmark(
    articleId: number
  ): Promise<{ data: LearningBookmarkToggleResponse }> {
    return client.post<LearningBookmarkToggleResponse>(
      `/learning/articles/${articleId}/bookmark`
    );
  },

  /** 标记已读（幂等；重复调用不改写首次时间戳）。 */
  markRead(articleId: number): Promise<{ data: LearningReadResponse }> {
    return client.post<LearningReadResponse>(
      `/learning/articles/${articleId}/read`
    );
  },

  /** 我的收藏列表（稍后读），bookmarked_at DESC。 */
  bookmarks(
    params: { page?: number; page_size?: number } = {}
  ): Promise<{ data: LearningFeedResponse }> {
    return client.get<LearningFeedResponse>('/learning/bookmarks', { params });
  },
};
