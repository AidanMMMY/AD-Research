import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useInfiniteQuery, useQuery, keepPreviousData } from '@tanstack/react-query';
import { Button, Spin, Tag } from 'antd';
import {
  learningApi,
  LEARNING_TOPIC_LABELS,
  LEARNING_TOPIC_ORDER,
  type LearningArticle,
  type LearningDifficulty,
} from '@/api/learning';
import type { NewsArticle } from '@/types/news';
import NewsCard from '@/components/NewsCard';
import NewsDetailDrawer from '@/components/NewsDetailDrawer';
import EmptyState from '@/components/EmptyState';
import LoadingBlock from '@/components/LoadingBlock';
import { useArticleStateActions } from './useArticleState';

const PAGE_SIZE = 20;

/** P2 难度筛选 chips（全部/入门/进阶）——'' 表示不过滤。 */
const DIFFICULTY_OPTIONS: { key: '' | LearningDifficulty; label: string }[] = [
  { key: '', label: '全部' },
  { key: 'beginner', label: '入门' },
  { key: 'advanced', label: '进阶' },
];

/**
 * 学习中心「知识库」feed (2026-08-02).
 *
 * Topic chip strip (中文标签 + 文章计数) + article list reusing the
 * shared ``NewsCard`` / ``NewsDetailDrawer`` from the /news page.
 * Ordering is server-side (importance first) — we render as-is.
 *
 * Resilience: the ``/learning/*`` endpoints may 404 while the backend
 * is still rolling out. Both queries use ``retry: 1`` and the feed
 * renders a friendly "准备中" empty state instead of an error banner,
 * so the page never breaks on empty / missing data.
 */
export default function KnowledgeFeed() {
  const navigate = useNavigate();
  const [topic, setTopic] = useState<string>('');
  const [difficulty, setDifficulty] = useState<'' | LearningDifficulty>('');
  const [selectedArticle, setSelectedArticle] = useState<NewsArticle | null>(null);

  // Per-topic counts for the chip strip. On failure we fall back to the
  // static taxonomy without counts — the feed below still works.
  const { data: topicsData } = useQuery({
    queryKey: ['learning-topics'],
    queryFn: () => learningApi.topics().then((r) => r.data),
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const topicChips = useMemo(() => {
    const counts = new Map<string, number>();
    for (const t of topicsData?.topics ?? []) {
      counts.set(t.topic, t.count);
    }
    // Union of the canonical taxonomy and any extra topics the backend
    // reports (so a new topic never hides just because the frontend
    // taxonomy lags).
    const keys: string[] = [...LEARNING_TOPIC_ORDER];
    for (const t of topicsData?.topics ?? []) {
      if (!keys.includes(t.topic)) keys.push(t.topic);
    }
    return keys.map((key) => ({
      key,
      label: LEARNING_TOPIC_LABELS[key] ?? key,
      count: counts.get(key),
    }));
  }, [topicsData]);

  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
    isError,
  } = useInfiniteQuery({
    queryKey: ['learning-feed', topic, difficulty],
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      learningApi
        .feed({
          topic: topic || undefined,
          difficulty: difficulty || undefined,
          page: pageParam,
          page_size: PAGE_SIZE,
          days: 90,
        })
        .then((r) => r.data),
    // The contract guarantees ``total``; ``page``/``page_size`` are
    // optional, so derive the next page from the accumulated item count
    // instead of trusting the echo.
    getNextPageParam: (last, allPages) => {
      const loaded = allPages.reduce((acc, p) => acc + (p?.items?.length ?? 0), 0);
      return loaded < (last?.total ?? 0) ? allPages.length + 1 : undefined;
    },
    // Keep the previous topic's list on screen while the next one
    // loads — no flash-of-empty on chip switch.
    placeholderData: keepPreviousData,
    retry: 1,
  });

  const articles = useMemo(() => {
    return (data?.pages ?? [])
      .flatMap((p) => p?.items ?? [])
      .filter((a): a is LearningArticle => a != null && typeof a === 'object');
  }, [data]);

  const total = data?.pages?.[0]?.total ?? 0;

  // Symbol chips on cards pivot to the full /news feed filtered by that
  // symbol (the knowledge feed has no per-symbol filter of its own).
  const handlePickSymbol = (sym: string) => {
    navigate(`/news?symbol=${encodeURIComponent(sym)}`);
  };

  // P1：收藏切换 + 打开详情自动已读（乐观更新，见 useArticleState）。
  const { toggleBookmark, markRead } = useArticleStateActions();

  return (
    <div className="learning-knowledge">
      {/* Topic chip strip — same visual language as the /news filter
          chips (global ``ad-status-chip`` styles).
          L1（2026-08-03）：行首加「主题：」前缀，与下方「难度：」对齐。 */}
      <div className="learning-topic-chips ad-flex ad-flex-wrap ad-gap-2 ad-mb-4">
        <span className="ad-text-small ad-text-tertiary ad-self-center ad-mr-1">
          主题：
        </span>
        <Tag.CheckableTag
          checked={topic === ''}
          onChange={() => setTopic('')}
          className={`ad-status-chip ${topic === '' ? 'ad-status-chip--active' : ''}`}
        >
          全部
        </Tag.CheckableTag>
        {topicChips.map((t) => {
          const checked = topic === t.key;
          return (
            <Tag.CheckableTag
              key={t.key}
              checked={checked}
              onChange={() => setTopic(checked ? '' : t.key)}
              className={`ad-status-chip ${checked ? 'ad-status-chip--active' : ''}`}
            >
              {t.label}
              {t.count != null && (
                <span className="learning-topic-chips__count"> {t.count}</span>
              )}
            </Tag.CheckableTag>
          );
        })}
      </div>

      {/* 难度筛选（P2）——后端按 news_source_meta.difficulty_default
          过滤，与主题筛选叠加生效。
          L1（2026-08-03）：行首加「难度：」前缀标签。 */}
      <div className="learning-topic-chips ad-flex ad-flex-wrap ad-gap-2 ad-mb-4">
        <span className="ad-text-small ad-text-tertiary ad-self-center ad-mr-1">
          难度：
        </span>
        {DIFFICULTY_OPTIONS.map((d) => {
          const checked = difficulty === d.key;
          return (
            <Tag.CheckableTag
              key={d.key || 'all'}
              checked={checked}
              onChange={() => setDifficulty(d.key)}
              className={`ad-status-chip ${checked ? 'ad-status-chip--active' : ''}`}
            >
              {d.label}
            </Tag.CheckableTag>
          );
        })}
      </div>

      {isError ? (
        /* API still rolling out (404) or backend down — stay calm. */
        <EmptyState
          title="知识库内容准备中"
          description="主题文章流正在接入，稍后回来即可看到按主题组织的深度文章。"
        />
      ) : isLoading ? (
        <div className="ad-p-5">
          <LoadingBlock size="lg" />
        </div>
      ) : articles.length === 0 ? (
        <EmptyState
          title="该主题暂无文章"
          description="换个主题看看，或稍后再来——知识库按近 90 天文章滚动更新。"
        />
      ) : (
        <>
          <div className="ad-text-small ad-text-tertiary ad-mb-3">
            共 {total} 篇 · 按重要性优先排序
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
