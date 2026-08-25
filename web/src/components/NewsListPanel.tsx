import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { List, Tag, Badge, Spin, Skeleton, Tooltip } from 'antd';
import { LinkOutlined, StarFilled } from '@ant-design/icons';
import { newsApi } from '@/api/news';
import type { NewsArticle, SentimentLabel } from '@/types/news';
import {
  formatDateTime,
  formatRelative as formatRelativeTz,
} from '@/utils/datetime';
import Panel from './Panel';
import EmptyState from './EmptyState';
import NewsDetailDrawer from './NewsDetailDrawer';

const SENTIMENT_COLORS: Record<SentimentLabel, string> = {
  positive: 'var(--color-rise)',
  neutral: 'var(--text-tertiary)',
  negative: 'var(--color-fall)',
};

const SENTIMENT_LABELS: Record<SentimentLabel, string> = {
  positive: '看多',
  neutral: '中性',
  negative: '看空',
};

export interface NewsListPanelProps {
  /** Stock / ETF / crypto code to filter by. */
  symbol: string;
  /** How many rows to show. */
  limit?: number;
  /** Hide the panel chrome (title bar). Useful when nested in a Tabs pane. */
  bare?: boolean;
}

function formatRelative(iso: string): string {
  // UTC-aware formatter — see ``utils/datetime``.
  return formatRelativeTz(iso, { withTimeAfterDays: 7 });
}

/**
 * Compact, embeddable news list for a single symbol. Used in the
 * ETF/Crypto detail tabs and any other context where a 5-10 row snippet
 * is enough. Full feed lives at ``/news?symbol=...``.
 */
export default function NewsListPanel({ symbol, limit = 10, bare = false }: NewsListPanelProps) {
  const navigate = useNavigate();
  // 阅读面板内选中的文章——与 /news 列表统一：点击原地开
  // NewsDetailDrawer，不再整页跳 /news/:id（抽屉页脚保留
  // 「打开完整页面」作为深链出口）。
  const [selected, setSelected] = useState<NewsArticle | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['news-by-symbol', symbol, limit],
    queryFn: () =>
      newsApi
        .list({ symbol, page: 1, page_size: limit })
        .then((r) => r.data.items),
    enabled: !!symbol,
    staleTime: 60_000,
  });

  const body = isError ? (
    <EmptyState title="加载失败" description="请稍后重试或检查网络" />
  ) : isLoading ? (
    <Skeleton active paragraph={{ rows: 4 }} />
  ) : !data || data.length === 0 ? (
    <EmptyState title={`暂无 ${symbol} 的相关资讯`} description="该标的暂时没有收录到有效资讯" />
  ) : (
    <List
      className="ad-list-compact"
      dataSource={data}
      renderItem={(a: NewsArticle) => {
        const filled = a.importance ? Math.max(0, Math.min(5, a.importance)) : 0;
        return (
          <List.Item
            className="news-list-panel__item"
            role="button"
            tabIndex={0}
            aria-label={`${a.title} — 打开资讯详情`}
            onClick={() => setSelected(a)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setSelected(a);
              }
            }}
          >
            <List.Item.Meta
              title={
                <div className="news-list-panel__title-row">
                  <span className="news-list-panel__title-text">
                    {a.title}
                  </span>
                  {a.sentiment_label && (
                    <Badge
                      color={SENTIMENT_COLORS[a.sentiment_label]}
                      text={
                        <span
                          className="news-list-panel__badge-text"
                          style={{ color: SENTIMENT_COLORS[a.sentiment_label] }}
                        >
                          {SENTIMENT_LABELS[a.sentiment_label]}
                        </span>
                      }
                    />
                  )}
                </div>
              }
              description={
                <div className="news-list-panel__meta">
                  <span className="news-list-panel__meta-text">{a.source}</span>
                  <span className="news-list-panel__meta-dot">·</span>
                  <Tooltip title={formatDateTime(a.published_at)}>
                    <span className="news-list-panel__meta-text">
                      {formatRelative(a.published_at)}
                    </span>
                  </Tooltip>
                  {a.importance && (
                    <span className="news-list-panel__importance">
                      {Array.from({ length: 5 }).map((_, i) => (
                        <StarFilled
                          key={i}
                          className={`news-list-panel__star ${i < filled ? 'news-list-panel__star--filled' : 'news-list-panel__star--empty'}`}
                        />
                      ))}
                    </span>
                  )}
                  {a.event_category && (
                    <Tag className="news-list-panel__category">{a.event_category}</Tag>
                  )}
                  <span className="news-list-panel__spacer" />
                  <Tooltip title="原文">
                    <LinkOutlined
                      className="news-list-panel__link"
                      onClick={(e) => {
                        e.stopPropagation();
                        window.open(a.url, '_blank', 'noopener,noreferrer');
                      }}
                    />
                  </Tooltip>
                </div>
              }
            />
          </List.Item>
        );
      }}
    />
  );

  // 面板内没有 feed 筛选语境——抽屉 chip 旁的筛选按钮退化为跳
  // /news?symbol=... 全量列表（与「查看全部」出口一致）。
  const drawer = (
    <NewsDetailDrawer
      article={selected}
      onClose={() => setSelected(null)}
      onPickSymbol={(sym) =>
        navigate(`/news?symbol=${encodeURIComponent(sym)}`)
      }
    />
  );

  if (bare)
    return (
      <div>
        {body}
        {drawer}
      </div>
    );

  return (
    <Panel
      variant="minimal"
      title="相关新闻"
      extra={
        <span
          className="news-list-panel__extra"
          onClick={() => navigate(`/news?symbol=${encodeURIComponent(symbol)}`)}
        >
          查看全部 →
        </span>
      }
      padding="md"
    >
      {body}
      {drawer}
    </Panel>
  );
}

/** Tiny inline loader wrapper for direct embed (no panel chrome). */
export function NewsListLoading() {
  return (
    <div className="news-list-panel__loader">
      <Spin />
    </div>
  );
}
