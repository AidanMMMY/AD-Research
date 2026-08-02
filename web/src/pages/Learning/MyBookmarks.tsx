import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useInfiniteQuery, keepPreviousData } from '@tanstack/react-query';
import { Button, Spin } from 'antd';
import { learningApi, type LearningArticle } from '@/api/learning';
import type { NewsArticle } from '@/types/news';
import NewsCard from '@/components/NewsCard';
import NewsDetailDrawer from '@/components/NewsDetailDrawer';
import EmptyState from '@/components/EmptyState';
import LoadingBlock from '@/components/LoadingBlock';
import { useArticleStateActions } from './useArticleState';

const PAGE_SIZE = 20;

/**
 * 学习中心「我的收藏」（稍后读）子视图（P1, 2026-08-02）。
 *
 * 数据来自 ``GET /learning/bookmarks``（bookmarked_at DESC）。
 * 在列表里点收藏按钮 = 取消收藏，乐观地把该项从列表移除
 * （见 ``useArticleState``）；打开详情抽屉同样自动标记已读。
 */
export default function MyBookmarks() {
  const navigate = useNavigate();
  const [selectedArticle, setSelectedArticle] = useState<NewsArticle | null>(null);
  const { toggleBookmark, markRead } = useArticleStateActions();

  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
    isError,
  } = useInfiniteQuery({
    queryKey: ['learning-bookmarks'],
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      learningApi
        .bookmarks({ page: pageParam, page_size: PAGE_SIZE })
        .then((r) => r.data),
    getNextPageParam: (last, allPages) => {
      const loaded = allPages.reduce((acc, p) => acc + (p?.items?.length ?? 0), 0);
      return loaded < (last?.total ?? 0) ? allPages.length + 1 : undefined;
    },
    placeholderData: keepPreviousData,
    retry: 1,
  });

  const articles = useMemo(() => {
    return (data?.pages ?? [])
      .flatMap((p) => p?.items ?? [])
      .filter((a): a is LearningArticle => a != null && typeof a === 'object');
  }, [data]);

  const total = data?.pages?.[0]?.total ?? 0;

  const handlePickSymbol = (sym: string) => {
    navigate(`/news?symbol=${encodeURIComponent(sym)}`);
  };

  return (
    <div className="learning-bookmarks">
      {isError ? (
        <EmptyState
          title="收藏列表加载失败"
          description="稍后重试，或先回到知识库继续阅读。"
        />
      ) : isLoading ? (
        <div className="ad-p-5">
          <LoadingBlock size="lg" />
        </div>
      ) : articles.length === 0 ? (
        <EmptyState
          title="还没有收藏"
          description="在知识库的文章卡片上点书签图标，把想稍后细读的文章收进来。"
        />
      ) : (
        <>
          <div className="ad-text-small ad-text-tertiary ad-mb-3">
            共 {total} 篇 · 按收藏时间倒序
          </div>
          <div className="ad-news-feed">
            {articles.map((a) => (
              <NewsCard
                key={a.id}
                article={a}
                onOpen={setSelectedArticle}
                onPickSymbol={handlePickSymbol}
                showBookmark
                onToggleBookmark={toggleBookmark}
                showDifficulty
              />
            ))}
          </div>
          <div className="learning-knowledge__more">
            {isFetchingNextPage ? (
              <Spin />
            ) : hasNextPage ? (
              <Button onClick={() => fetchNextPage()}>加载更多</Button>
            ) : (
              <span className="ad-text-small ad-text-tertiary">— 已加载全部 —</span>
            )}
          </div>
        </>
      )}

      <NewsDetailDrawer
        article={selectedArticle}
        onClose={() => setSelectedArticle(null)}
        onPickSymbol={handlePickSymbol}
        onRead={markRead}
      />
    </div>
  );
}
