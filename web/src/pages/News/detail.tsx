import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Spin,
  Alert,
  Tag,
  Badge,
  Space,
  Button,
  Skeleton,
  List,
  Tooltip,
} from 'antd';
import {
  ArrowLeftOutlined,
  LinkOutlined,
  StarFilled,
  LikeOutlined,
  MessageOutlined,
  ShareAltOutlined,
  EyeOutlined,
  BulbOutlined,
  ReadOutlined,
  MessageOutlined as ChatOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { newsApi } from '@/api/news';
import type {
  NewsArticle,
  NewsFetchContentResponse,
  SentimentLabel,
  ImportanceLevel,
} from '@/types/news';
import PageShell from '@/components/PageShell';
import Panel from '@/components/Panel';
import Markdown from '@/components/Markdown';
import EmptyState from '@/components/EmptyState';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import StatCard from '@/components/StatCard';

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

const SOCIAL_SOURCES = new Set(['xueqiu', 'reddit', 'weibo']);

const IMPORTANCE_COLOR = 'var(--color-warning-bright)';

function ImportanceStars({ level }: { level: ImportanceLevel | null }) {
  if (!level) return null;
  const filled = Math.max(0, Math.min(5, level));
  return (
    <Tooltip title={`重要性 ${level}/5`}>
      <span className="ad-text-sm ad-letter-spacing">
        {Array.from({ length: 5 }).map((_, i) => (
          <StarFilled
            key={i}
            className="ad-text-sm"
            style={{
              color: i < filled ? IMPORTANCE_COLOR : 'var(--text-muted)',
              opacity: i < filled ? 1 : 0.4,
              marginRight: 1,
            }}
          />
        ))}
      </span>
    </Tooltip>
  );
}

function formatBigNumber(n: number | undefined): string {
  if (n == null) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export default function NewsDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const articleId = Number(id);
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['news-detail', articleId],
    queryFn: () => newsApi.get(articleId).then((r) => r.data),
    enabled: Number.isFinite(articleId) && articleId > 0,
  });

  // Local override: once the user clicks "load full text" we want the
  // rendered body to switch from the cached intro to the Jina-fetched
  // Markdown without forcing a full refetch of the article.
  const [renderedFullContent, setRenderedFullContent] =
    useState<string | null>(null);

  // Reset the override when navigating between articles.
  useEffect(() => {
    setRenderedFullContent(null);
  }, [articleId]);

  // Fetch related articles for each mentioned symbol.
  const symbols = data?.symbols ?? [];
  const [primarySymbol, ...otherSymbols] = symbols.map((s) => s.symbol);

  const { data: related, isLoading: relatedLoading } = useQuery({
    queryKey: ['news-related', primarySymbol, articleId],
    queryFn: () =>
      primarySymbol
        ? newsApi
            .list({ symbol: primarySymbol, page: 1, page_size: 6 })
            .then((r) => r.data.items.filter((a) => a.id !== articleId).slice(0, 5))
        : Promise.resolve([] as NewsArticle[]),
    enabled: !!primarySymbol,
  });

  // Lazy full-text fetch via Jina Reader. The button shows a spinner
  // for 5-15s while we wait for r.jina.ai to return Markdown.
  const fetchFullContent = useMutation({
    mutationFn: (): Promise<NewsFetchContentResponse> =>
      newsApi.fetchContent(articleId).then((r) => r.data),
    onSuccess: (resp) => {
      if (resp.success && resp.content) {
        setRenderedFullContent(resp.content);
        // Best-effort refresh of the article detail so a subsequent
        // mount gets the cached version too.
        queryClient.invalidateQueries({ queryKey: ['news-detail', articleId] });
      }
    },
  });

  // Update document title for nicer browser tab.
  useEffect(() => {
    if (data?.title) {
      document.title = `${data.title} - 资讯`;
    }
    return () => {
      document.title = '投研平台';
    };
  }, [data?.title]);

  if (isLoading) {
    return (
      <PageShell maxWidth="reading">
        <div className="ad-p-15 ad-text-center">
          <Spin size="large" />
        </div>
      </PageShell>
    );
  }
  if (error || !data) {
    return (
      <PageShell maxWidth="reading">
        <Alert
          type="error"
          message="加载资讯失败"
          description={(error as Error | undefined)?.message ?? '资讯不存在或已被删除'}
          showIcon
        />
        <Button
          className="ad-mt-4"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/news')}
        >
          返回资讯列表
        </Button>
      </PageShell>
    );
  }

  const showSocial = SOCIAL_SOURCES.has(data.source);
  const sentiment = data.sentiment_label;
  const fetchedAt = data.full_content_fetched_at;
  const fullContentCached = data.full_content && !renderedFullContent;
  const showFetchError =
    fetchFullContent.isError ||
    (fetchFullContent.data && !fetchFullContent.data.success);
  const fullContentToRender = renderedFullContent ?? data.full_content;

  return (
    <PageShell maxWidth="reading">
      {/* Header */}
      <header className="ad-detail-header">
        <Button
          type="text"
          size="small"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/news')}
          className="ad-mb-3 ad-p-0"
        >
          返回资讯
        </Button>
        <div className="ad-detail-meta">
          <span>{data.source}</span>
          <span className="ad-detail-meta__divider">·</span>
          <span>{dayjs(data.published_at).format('YYYY-MM-DD HH:mm')}</span>
          <span className="ad-detail-meta__divider">·</span>
          <span>{data.language}</span>
          {data.author && (
            <>
              <span className="ad-detail-meta__divider">·</span>
              <span>{data.author}</span>
            </>
          )}
          <span className="ad-flex-1" />
          <ImportanceStars level={data.importance} />
        </div>

        <h1 className="ad-detail-title">
          {data.title}
        </h1>

        <div className="ad-detail-actions">
          {symbols.length > 0 && (
            <Space size={4} wrap>
              {symbols.map((s) => (
                <Tag
                  key={`${s.symbol}-${s.match_type}`}
                  color="default"
                  className="ad-detail-tag"
                >
                  {s.symbol}
                </Tag>
              ))}
            </Space>
          )}
          {data.event_category && (
            <Tag color="geekblue" className="ad-detail-tag">
              {data.event_category}
            </Tag>
          )}
          {sentiment && (
            <Badge
              color={SENTIMENT_COLORS[sentiment]}
              text={
                <span
                  className="ad-sentiment-label--detail"
                  style={{ color: SENTIMENT_COLORS[sentiment] }}
                >
                  {SENTIMENT_LABELS[sentiment]}
                  {data.sentiment_score != null &&
                    ` · ${data.sentiment_score.toFixed(2)}`}
                </span>
              }
            />
          )}
          <span className="ad-flex-1" />
          <Button
            type="primary"
            icon={<LinkOutlined />}
            onClick={() => window.open(data.url, '_blank', 'noopener,noreferrer')}
          >
            查看原文
          </Button>
        </div>
      </header>

      <div className="ad-detail-grid">
        {/* Body */}
        <div>
          <article className="ad-detail-article">
            {fullContentToRender ? (
              // Cache hit (from a previous click) OR we just finished
              // fetching — render the Markdown body inline.
              <Markdown source={fullContentToRender} />
            ) : data.body ? (
              <div className="ad-detail-article__body">
                {data.body}
              </div>
            ) : (
              <EmptyState title="暂无正文，请前往原文查看完整内容" />
            )}

            {/* Load-full-text control: only when we don't already have
                a rendered full body. The summary that the crawler gave
                us is usually just an excerpt, so users need an explicit
                way to see the whole article. */}
            {!fullContentToRender && (
              <div className="ad-mt-5 ad-text-center">
                <Button
                  type="default"
                  size="large"
                  icon={<ReadOutlined />}
                  loading={fetchFullContent.isPending}
                  onClick={() => fetchFullContent.mutate()}
                >
                  {fetchFullContent.isPending
                    ? '正在抓取全文…'
                    : '📖 加载完整正文'}
                </Button>
                <div className="ad-mt-2 ad-text-small ad-text-tertiary">
                  通过 Jina Reader 在线抓取，通常 5-15 秒
                </div>
              </div>
            )}

            {fetchedAt && (
              <div className="ad-mt-3 ad-text-small ad-text-muted">
                全文缓存于 {dayjs(fetchedAt).format('YYYY-MM-DD HH:mm')}
                {fullContentCached ? ' · 已缓存' : ''}
              </div>
            )}

            {showFetchError && (
              <Alert
                className="ad-mt-4"
                type="warning"
                showIcon
                message="全文抓取失败"
                description={
                  fetchFullContent.isError
                    ? (fetchFullContent.error as Error | undefined)?.message
                    : fetchFullContent.data?.error
                }
              />
            )}
          </article>

          {/* Sentiment drivers / LLM summary */}
          {(data.sentiment_drivers?.length || (data.sentiment_confidence != null)) && (
            <Panel
              variant="default"
              title={
                <span>
                  <BulbOutlined className="ad-icon-accent" />
                  情绪解读
                </span>
              }
              className="ad-mt-5"
              padding="md"
            >
              {data.sentiment_confidence != null && (
                <div className="ad-flex ad-items-center ad-gap-3 ad-mb-3">
                  <span className="ad-text-small ad-text-tertiary">
                    LLM 置信度
                  </span>
                  <div className="ad-sentiment-bar ad-flex-1" style={{ maxWidth: 240 }}>
                    <div
                      className="ad-sentiment-bar__fill"
                      style={{
                        width: `${data.sentiment_confidence * 100}%`,
                        background: sentiment ? SENTIMENT_COLORS[sentiment] : 'var(--text-secondary)',
                      }}
                    />
                    <div className="ad-sentiment-bar__center" />
                  </div>
                  <span
                    className="font-mono ad-text-small ad-text-primary"
                  >
                    {(data.sentiment_confidence * 100).toFixed(0)}%
                  </span>
                </div>
              )}
              {data.sentiment_drivers && data.sentiment_drivers.length > 0 && (
                <div>
                  <div className="ad-text-small ad-text-tertiary ad-mb-2">
                    关键驱动
                  </div>
                  <Space wrap>
                    {data.sentiment_drivers.map((d) => (
                      <Tag key={d} color="default" className="ad-detail-tag">
                        {d}
                      </Tag>
                    ))}
                  </Space>
                </div>
              )}
            </Panel>
          )}

          {/* Social discussion placeholder (xueqiu/reddit). */}
          {showSocial && (
            <Panel
              variant="default"
              title={
                <span>
                  <ChatOutlined className="ad-icon-mr" />
                  散户讨论
                </span>
              }
              className="ad-mt-5"
              padding="md"
            >
              <EmptyState title="散户讨论内容由 Agent E 后续接入" />
            </Panel>
          )}
        </div>

        {/* Right column: meta + related */}
        <div className="dashboard-side-stack">
          {/* Engagement */}
          <Panel variant="default" title="互动数据" padding="md">
            <ResponsiveGrid cols={2} gap="sm">
              <StatCard
                title="点赞"
                value={formatBigNumber(data.engagement?.likes)}
                icon={<LikeOutlined />}
                bordered={false}
              />
              <StatCard
                title="评论"
                value={formatBigNumber(data.engagement?.comments)}
                icon={<MessageOutlined />}
                bordered={false}
              />
              <StatCard
                title="转发"
                value={formatBigNumber(data.engagement?.shares)}
                icon={<ShareAltOutlined />}
                bordered={false}
              />
              <StatCard
                title="阅读"
                value={formatBigNumber(data.engagement?.views)}
                icon={<EyeOutlined />}
                bordered={false}
              />
            </ResponsiveGrid>
          </Panel>

          {/* Other symbols mentioned */}
          {otherSymbols.length > 0 && (
            <Panel variant="default" title="其他提及标的" padding="md">
              <Space wrap>
                {otherSymbols.map((sym) => (
                  <Link key={sym} to={`/news?symbol=${encodeURIComponent(sym)}`}>
                    <Tag className="ad-detail-tag ad-chip-tag">{sym}</Tag>
                  </Link>
                ))}
              </Space>
            </Panel>
          )}

          {/* Related articles */}
          <Panel
            variant="default"
            title={
              primarySymbol ? `相关资讯 · ${primarySymbol}` : '相关资讯'
            }
            padding="md"
          >
            {relatedLoading ? (
              <Skeleton active paragraph={{ rows: 4 }} />
            ) : !related || related.length === 0 ? (
              <EmptyState title="暂无相关资讯" />
            ) : (
              <List
                dataSource={related}
                renderItem={(item) => (
                  <List.Item
                    className="ad-cursor-pointer"
                    onClick={() => navigate(`/news/${item.id}`)}
                  >
                    <List.Item.Meta
                      title={
                        <div className="ad-line-clamp-2 ad-text-sm ad-text-primary ad-leading-normal">
                          {item.title}
                        </div>
                      }
                      description={
                        <div className="ad-flex ad-items-center ad-gap-2 ad-mt-2">
                          <span className="ad-text-small ad-text-tertiary">
                            {item.source}
                          </span>
                          <span className="ad-text-small ad-text-muted">·</span>
                          <span className="ad-text-small ad-text-tertiary">
                            {dayjs(item.published_at).format('MM-DD HH:mm')}
                          </span>
                          {item.sentiment_label && (
                            <span
                              className="ad-text-small ad-ml-auto"
                              style={{ color: SENTIMENT_COLORS[item.sentiment_label] }}
                            >
                              {SENTIMENT_LABELS[item.sentiment_label]}
                            </span>
                          )}
                        </div>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Panel>
        </div>
      </div>
    </PageShell>
  );
}
