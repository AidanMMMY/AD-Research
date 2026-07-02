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
  Empty,
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
import Panel from '@/components/Panel';
import Markdown from '@/components/Markdown';

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
      <span style={{ fontSize: 13, letterSpacing: 1 }}>
        {Array.from({ length: 5 }).map((_, i) => (
          <StarFilled
            key={i}
            style={{
              color: i < filled ? IMPORTANCE_COLOR : 'var(--text-muted)',
              opacity: i < filled ? 1 : 0.4,
              fontSize: 13,
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
      <div style={{ padding: 60, textAlign: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }
  if (error || !data) {
    return (
      <div style={{ padding: 24 }}>
        <Alert
          type="error"
          message="加载资讯失败"
          description={(error as Error | undefined)?.message ?? '资讯不存在或已被删除'}
          showIcon
        />
        <Button
          style={{ marginTop: 16 }}
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/news')}
        >
          返回资讯列表
        </Button>
      </div>
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
    <div>
      {/* Header */}
      <div
        style={{
          borderBottom: '1px solid var(--border-default)',
          paddingBottom: 20,
          marginBottom: 24,
        }}
      >
        <Button
          type="text"
          size="small"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/news')}
          style={{ marginBottom: 12, padding: 0 }}
        >
          返回资讯
        </Button>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-3)',
            fontSize: 12,
            color: 'var(--text-tertiary)',
            marginBottom: 12,
          }}
        >
          <span>{data.source}</span>
          <span style={{ color: 'var(--text-muted)' }}>·</span>
          <span>{dayjs(data.published_at).format('YYYY-MM-DD HH:mm')}</span>
          <span style={{ color: 'var(--text-muted)' }}>·</span>
          <span>{data.language}</span>
          {data.author && (
            <>
              <span style={{ color: 'var(--text-muted)' }}>·</span>
              <span>{data.author}</span>
            </>
          )}
          <span style={{ flex: 1 }} />
          <ImportanceStars level={data.importance} />
        </div>

        <h1
          style={{
            fontSize: 'var(--text-h1-size)',
            fontWeight: 600,
            color: 'var(--text-primary)',
            margin: 0,
            letterSpacing: '-0.02em',
            lineHeight: 1.4,
          }}
        >
          {data.title}
        </h1>

        <div
          style={{
            marginTop: 16,
            display: 'flex',
            gap: 12,
            flexWrap: 'wrap',
            alignItems: 'center',
          }}
        >
          {symbols.length > 0 && (
            <Space size={4} wrap>
              {symbols.map((s) => (
                <Tag
                  key={`${s.symbol}-${s.match_type}`}
                  color="default"
                  style={{ margin: 0, fontSize: 12 }}
                >
                  {s.symbol}
                </Tag>
              ))}
            </Space>
          )}
          {data.event_category && (
            <Tag color="geekblue" style={{ margin: 0, fontSize: 12 }}>
              {data.event_category}
            </Tag>
          )}
          {sentiment && (
            <Badge
              color={SENTIMENT_COLORS[sentiment]}
              text={
                <span
                  style={{
                    color: SENTIMENT_COLORS[sentiment],
                    fontSize: 13,
                    fontWeight: 500,
                  }}
                >
                  {SENTIMENT_LABELS[sentiment]}
                  {data.sentiment_score != null &&
                    ` · ${data.sentiment_score.toFixed(2)}`}
                </span>
              }
            />
          )}
          <span style={{ flex: 1 }} />
          <Button
            type="primary"
            icon={<LinkOutlined />}
            onClick={() => window.open(data.url, '_blank', 'noopener,noreferrer')}
          >
            查看原文
          </Button>
        </div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) 320px',
          gap: 24,
        }}
      >
        {/* Body */}
        <div>
          <article
            style={{
              background: 'var(--card-bg)',
              border: '1px solid var(--card-border)',
              borderRadius: 'var(--card-radius)',
              padding: 'var(--space-5) var(--space-6)',
            }}
          >
            {fullContentToRender ? (
              // Cache hit (from a previous click) OR we just finished
              // fetching — render the Markdown body inline.
              <Markdown source={fullContentToRender} />
            ) : data.body ? (
              <div
                style={{
                  fontSize: 15,
                  lineHeight: 1.7,
                  color: 'var(--text-primary)',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {data.body}
              </div>
            ) : (
              <Empty description="暂无正文，请前往原文查看完整内容" />
            )}

            {/* Load-full-text control: only when we don't already have
                a rendered full body. The summary that the crawler gave
                us is usually just an excerpt, so users need an explicit
                way to see the whole article. */}
            {!fullContentToRender && (
              <div style={{ marginTop: 20, textAlign: 'center' }}>
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
                <div
                  style={{
                    marginTop: 8,
                    fontSize: 12,
                    color: 'var(--text-tertiary)',
                  }}
                >
                  通过 Jina Reader 在线抓取，通常 5-15 秒
                </div>
              </div>
            )}

            {fetchedAt && (
              <div
                style={{
                  marginTop: 14,
                  fontSize: 12,
                  color: 'var(--text-muted)',
                }}
              >
                全文缓存于 {dayjs(fetchedAt).format('YYYY-MM-DD HH:mm')}
                {fullContentCached ? ' · 已缓存' : ''}
              </div>
            )}

            {showFetchError && (
              <Alert
                style={{ marginTop: 16 }}
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
              variant="minimal"
              title={
                <span>
                  <BulbOutlined style={{ marginRight: 6, color: 'var(--accent)' }} />
                  情绪解读
                </span>
              }
              style={{ marginTop: 20 }}
              padding="md"
            >
              {data.sentiment_confidence != null && (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    marginBottom: 12,
                  }}
                >
                  <span style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>
                    LLM 置信度
                  </span>
                  <div
                    style={{
                      flex: 1,
                      maxWidth: 240,
                      height: 6,
                      borderRadius: 3,
                      background: 'var(--bg-input)',
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        width: `${data.sentiment_confidence * 100}%`,
                        height: '100%',
                        background:
                          sentiment ? SENTIMENT_COLORS[sentiment] : 'var(--text-secondary)',
                      }}
                    />
                  </div>
                  <span
                    style={{
                      fontSize: 13,
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--text-primary)',
                    }}
                  >
                    {(data.sentiment_confidence * 100).toFixed(0)}%
                  </span>
                </div>
              )}
              {data.sentiment_drivers && data.sentiment_drivers.length > 0 && (
                <div>
                  <div
                    style={{
                      fontSize: 12,
                      color: 'var(--text-tertiary)',
                      marginBottom: 8,
                    }}
                  >
                    关键驱动
                  </div>
                  <Space wrap>
                    {data.sentiment_drivers.map((d) => (
                      <Tag key={d} color="default" style={{ fontSize: 12 }}>
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
              variant="minimal"
              title={
                <span>
                  <ChatOutlined style={{ marginRight: 6 }} />
                  散户讨论
                </span>
              }
              style={{ marginTop: 20 }}
              padding="md"
            >
              <Empty
                description="散户讨论内容由 Agent E 后续接入"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            </Panel>
          )}
        </div>

        {/* Right column: meta + related */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Engagement */}
          <Panel variant="minimal" title="互动数据" padding="md">
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(2, 1fr)',
                gap: 12,
              }}
            >
              {[
                { icon: <LikeOutlined />, label: '点赞', value: data.engagement?.likes },
                { icon: <MessageOutlined />, label: '评论', value: data.engagement?.comments },
                { icon: <ShareAltOutlined />, label: '转发', value: data.engagement?.shares },
                { icon: <EyeOutlined />, label: '阅读', value: data.engagement?.views },
              ].map((m) => (
                <div
                  key={m.label}
                  style={{
                    padding: 'var(--space-3) var(--space-3)',
                    background: 'var(--bg-elevated)',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border-default)',
                  }}
                >
                  <div
                    style={{
                      fontSize: 11,
                      color: 'var(--text-tertiary)',
                      marginBottom: 4,
                    }}
                  >
                    {m.icon} {m.label}
                  </div>
                  <div
                    style={{
                      fontSize: 16,
                      fontWeight: 600,
                      color: 'var(--text-primary)',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    {formatBigNumber(m.value)}
                  </div>
                </div>
              ))}
            </div>
          </Panel>

          {/* Other symbols mentioned */}
          {otherSymbols.length > 0 && (
            <Panel variant="minimal" title="其他提及标的" padding="md">
              <Space wrap>
                {otherSymbols.map((sym) => (
                  <Link key={sym} to={`/news?symbol=${encodeURIComponent(sym)}`}>
                    <Tag style={{ cursor: 'pointer', fontSize: 12 }}>{sym}</Tag>
                  </Link>
                ))}
              </Space>
            </Panel>
          )}

          {/* Related articles */}
          <Panel
            variant="minimal"
            title={
              primarySymbol ? `相关资讯 · ${primarySymbol}` : '相关资讯'
            }
            padding="md"
          >
            {relatedLoading ? (
              <Skeleton active paragraph={{ rows: 4 }} />
            ) : !related || related.length === 0 ? (
              <Empty
                description="暂无相关资讯"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            ) : (
              <List
                dataSource={related}
                renderItem={(item) => (
                  <List.Item
                    style={{ padding: '8px 0', cursor: 'pointer' }}
                    onClick={() => navigate(`/news/${item.id}`)}
                  >
                    <List.Item.Meta
                      title={
                        <div
                          style={{
                            fontSize: 13,
                            color: 'var(--text-primary)',
                            lineHeight: 1.5,
                            display: '-webkit-box',
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: 'vertical',
                            overflow: 'hidden',
                          }}
                        >
                          {item.title}
                        </div>
                      }
                      description={
                        <div
                          style={{
                            display: 'flex',
                            gap: 8,
                            alignItems: 'center',
                            marginTop: 4,
                          }}
                        >
                          <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                            {item.source}
                          </span>
                          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>·</span>
                          <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                            {dayjs(item.published_at).format('MM-DD HH:mm')}
                          </span>
                          {item.sentiment_label && (
                            <span
                              style={{
                                fontSize: 11,
                                color: SENTIMENT_COLORS[item.sentiment_label],
                                marginLeft: 'auto',
                              }}
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
    </div>
  );
}
