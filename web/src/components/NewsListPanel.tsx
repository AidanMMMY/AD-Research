import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { List, Tag, Badge, Spin, Empty, Skeleton, Tooltip } from 'antd';
import { LinkOutlined, StarFilled } from '@ant-design/icons';
import dayjs from 'dayjs';
import { newsApi } from '@/api/news';
import type { NewsArticle, SentimentLabel } from '@/types/news';
import Panel from './Panel';

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
  const t = dayjs(iso);
  if (!t.isValid()) return '';
  const diff = dayjs().diff(t, 'minute');
  if (diff < 60) return `${diff < 1 ? '刚刚' : `${diff} 分钟前`}`;
  const h = Math.floor(diff / 60);
  if (h < 24) return `${h} 小时前`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d} 天前`;
  return t.format('MM-DD');
}

/**
 * Compact, embeddable news list for a single symbol. Used in the
 * ETF/Crypto detail tabs and any other context where a 5-10 row snippet
 * is enough. Full feed lives at ``/news?symbol=...``.
 */
export default function NewsListPanel({ symbol, limit = 10, bare = false }: NewsListPanelProps) {
  const navigate = useNavigate();

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
    <Empty description="加载失败" image={Empty.PRESENTED_IMAGE_SIMPLE} />
  ) : isLoading ? (
    <Skeleton active paragraph={{ rows: 4 }} />
  ) : !data || data.length === 0 ? (
    <Empty description={`暂无 ${symbol} 的相关资讯`} image={Empty.PRESENTED_IMAGE_SIMPLE} />
  ) : (
    <List
      dataSource={data}
      renderItem={(a: NewsArticle) => {
        const filled = a.importance ? Math.max(0, Math.min(5, a.importance)) : 0;
        return (
          <List.Item
            className="news-list-panel__item"
            onClick={() => navigate(`/news/${a.id}`)}
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
                  <Tooltip title={dayjs(a.published_at).format('YYYY-MM-DD HH:mm')}>
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

  if (bare) return <div>{body}</div>;

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
