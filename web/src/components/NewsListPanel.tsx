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

const IMPORTANCE_COLOR = 'var(--color-warning-bright)';

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
            style={{ padding: '12px 0', cursor: 'pointer' }}
            onClick={() => navigate(`/news/${a.id}`)}
          >
            <List.Item.Meta
              title={
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    fontSize: 13,
                    color: 'var(--text-primary)',
                    lineHeight: 1.5,
                  }}
                >
                  <span
                    style={{
                      flex: 1,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {a.title}
                  </span>
                  {a.sentiment_label && (
                    <Badge
                      color={SENTIMENT_COLORS[a.sentiment_label]}
                      text={
                        <span
                          style={{
                            fontSize: 11,
                            color: SENTIMENT_COLORS[a.sentiment_label],
                            fontWeight: 500,
                          }}
                        >
                          {SENTIMENT_LABELS[a.sentiment_label]}
                        </span>
                      }
                    />
                  )}
                </div>
              }
              description={
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    marginTop: 4,
                    flexWrap: 'wrap',
                  }}
                >
                  <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                    {a.source}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>·</span>
                  <Tooltip title={dayjs(a.published_at).format('YYYY-MM-DD HH:mm')}>
                    <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                      {formatRelative(a.published_at)}
                    </span>
                  </Tooltip>
                  {a.importance && (
                    <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
                      {Array.from({ length: 5 }).map((_, i) => (
                        <StarFilled
                          key={i}
                          style={{
                            color: i < filled ? IMPORTANCE_COLOR : 'var(--text-muted)',
                            opacity: i < filled ? 1 : 0.4,
                            fontSize: 9,
                            marginRight: 1,
                          }}
                        />
                      ))}
                    </span>
                  )}
                  {a.event_category && (
                    <Tag style={{ margin: 0, fontSize: 10 }}>{a.event_category}</Tag>
                  )}
                  <span style={{ flex: 1 }} />
                  <Tooltip title="原文">
                    <LinkOutlined
                      style={{ fontSize: 12, color: 'var(--text-tertiary)' }}
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
          style={{ fontSize: 12, color: 'var(--text-tertiary)', cursor: 'pointer' }}
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
    <div style={{ textAlign: 'center', padding: 40 }}>
      <Spin />
    </div>
  );
}
