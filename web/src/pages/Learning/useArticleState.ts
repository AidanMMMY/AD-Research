import { useCallback } from 'react';
import { useQueryClient, type InfiniteData } from '@tanstack/react-query';
import { learningApi, type LearningFeedResponse } from '@/api/learning';
import type { NewsArticle } from '@/types/news';

/**
 * 学习中心 P1（2026-08-02）：收藏（稍后读）/ 已读的共享操作 hook。
 *
 * 知识库 feed（``['learning-feed', topic]`` 无限分页）与收藏列表
 * （``['learning-bookmarks']``）共用同一套乐观更新逻辑：
 *
 * - 点击收藏：立即翻转卡片上的 ``bookmarked`` 布尔；若当前在收藏
 *   列表里取消收藏，同时把该项从列表页中移除并递减 total。
 * - 打开详情：立即把 ``read`` 置 true（后端首次时间戳不刷新，
 *   所以前端重复置 true 是安全的幂等操作）。
 * - API 失败：invalidate 相关查询回滚到服务端真实状态。
 *
 * 乐观更新直接改 react-query 缓存而非本地 state，因此跨分页、跨
 * Tab（知识库 ↔ 我的收藏）状态天然一致。
 */

type FeedInfinite = InfiniteData<LearningFeedResponse>;

/** 对无限分页缓存里所有页的 items 做一次映射。 */
function mapFeedItems(
  data: FeedInfinite | undefined,
  fn: (a: NewsArticle) => NewsArticle | null
): FeedInfinite | undefined {
  if (!data) return data;
  return {
    ...data,
    pages: data.pages.map((p) => {
      const next: NewsArticle[] = [];
      let removed = 0;
      for (const item of p.items) {
        const mapped = fn(item);
        if (mapped == null) {
          removed += 1;
        } else {
          next.push(mapped);
        }
      }
      return {
        ...p,
        items: next as LearningFeedResponse['items'],
        total: Math.max(0, (p.total ?? 0) - removed),
      };
    }),
  };
}

export function useArticleStateActions() {
  const queryClient = useQueryClient();

  /** 回滚：乐观更新失败时让两个列表重新拉服务端真实状态。 */
  const rollback = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['learning-feed'] });
    queryClient.invalidateQueries({ queryKey: ['learning-bookmarks'] });
  }, [queryClient]);

  const toggleBookmark = useCallback(
    (article: NewsArticle) => {
      const nextBookmarked = !(article.bookmarked ?? false);

      // 1) 知识库 feed：翻转该篇的 bookmarked 布尔（所有 topic 变体）
      queryClient.setQueriesData<FeedInfinite>(
        { queryKey: ['learning-feed'] },
        (data) =>
          mapFeedItems(data, (a) =>
            a.id === article.id ? { ...a, bookmarked: nextBookmarked } : a
          )
      );

      // 2) 收藏列表：取消收藏时把该项从列表移除；收藏时不插入
      //    （新收藏应排在最前，但当前页顺序无法预知——交给下次
      //    invalidate / 重新进入该 Tab 时拉取）。
      queryClient.setQueriesData<FeedInfinite>(
        { queryKey: ['learning-bookmarks'] },
        (data) =>
          mapFeedItems(data, (a) => {
            if (a.id !== article.id) return a;
            return nextBookmarked ? { ...a, bookmarked: true } : null;
          })
      );

      learningApi.toggleBookmark(article.id).catch(rollback);
    },
    [queryClient, rollback]
  );

  const markRead = useCallback(
    (article: NewsArticle) => {
      if (article.read) return; // 已读就不再发请求（幂等短路）

      const mark = (a: NewsArticle) =>
        a.id === article.id ? { ...a, read: true } : a;
      queryClient.setQueriesData<FeedInfinite>(
        { queryKey: ['learning-feed'] },
        (data) => mapFeedItems(data, mark)
      );
      queryClient.setQueriesData<FeedInfinite>(
        { queryKey: ['learning-bookmarks'] },
        (data) => mapFeedItems(data, mark)
      );

      learningApi.markRead(article.id).catch(rollback);
    },
    [queryClient, rollback]
  );

  return { toggleBookmark, markRead };
}
