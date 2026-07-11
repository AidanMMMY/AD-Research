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
  Switch,
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
  TranslationOutlined,
  MessageOutlined as ChatOutlined,
} from '@ant-design/icons';
import { newsApi } from '@/api/news';
import type {
  NewsArticle,
  NewsFetchContentResponse,
  NewsTranslateResponse,
  ImportanceLevel,
} from '@/types/news';
import './detail.css';
import PageShell from '@/components/PageShell';
import Panel from '@/components/Panel';
import Markdown from '@/components/Markdown';
import EmptyState from '@/components/EmptyState';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import StatCard from '@/components/StatCard';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import { formatDateTime, formatDateTimeCompact } from '@/utils/datetime';
import { SENTIMENT_COLORS, SENTIMENT_LABELS } from '@/utils/sentiment';
import HelpPopover from '@/components/HelpPopover';
import { useSettingsStore } from '@/stores/settings';

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
            className="ad-text-sm news-importance-star"
            style={{
              color: i < filled ? IMPORTANCE_COLOR : 'var(--text-muted)',
              opacity: i < filled ? 1 : 0.4,
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
  const mode = useSettingsStore((s) => s.mode);

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
  const [primarySymbolObj, ...otherSymbols] = symbols;
  const primarySymbol = primarySymbolObj?.symbol;

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

  // AI translation toggle. Only enabled for English articles; the
  // server enforces ``language == 'en'`` and we mirror that here so
  // non-English articles never show the toggle at all.
  const [showTranslation, setShowTranslation] = useState(false);
  const [translationOverride, setTranslationOverride] = useState<string | null>(
    null,
  );
  const isEnglish = (data?.language || '').toLowerCase() === 'en';

  // Reset the toggle + override when navigating between articles so a
  // fresh article doesn't inherit the previous one's translation.
  useEffect(() => {
    setShowTranslation(false);
    setTranslationOverride(null);
  }, [articleId]);

  const translateArticle = useMutation({
    mutationFn: (): Promise<NewsTranslateResponse> =>
      newsApi.translate(articleId).then((r) => r.data),
    onSuccess: (resp) => {
      setTranslationOverride(resp.translation);
      // Refresh the article detail so a subsequent mount picks up the
      // cached translation without an extra round-trip.
      queryClient.invalidateQueries({ queryKey: ['news-detail', articleId] });
    },
  });

  // When the toggle flips on, kick off the translation if we don't
  // already have one cached on the article (or in local state).
  const translationFromServer = data?.translated_zh ?? null;
  const translationToShow = translationOverride ?? translationFromServer;
  const handleTranslationToggle = (checked: boolean) => {
    setShowTranslation(checked);
    if (checked && !translationToShow && !translateArticle.isPending) {
      translateArticle.mutate();
    }
  };

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
      <PageShell maxWidth="full">
        <div className="ad-p-15 ad-text-center">
          <Spin size="large" />
        </div>
      </PageShell>
    );
  }
  if (error || !data) {
    return (
      <PageShell maxWidth="full">
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

  // AI-cleanup observability banner (M22-3, 2026-07-05).
  //
  // Until now the DeepSeek call in ContentFetcher._clean_with_ai
  // could silently fail and the row would happily show the raw Jina
  // Markdown. The backend now records ``ai_cleanup_status`` so we can
  // render one of three banners above the body:
  //   * cleaned       → no banner (default).
  //   * skipped       → grey "AI 暂不可用, 已保留原始抓取".
  //   * failed        → red "AI 清理失败, 已保留原始抓取".
  //   * null / not_attempted → yellow "该篇尚未抓取正文".
  const aiStatus = data.ai_cleanup_status ?? null;
  const aiBanner =
    aiStatus === 'failed'
      ? {
          type: 'error' as const,
          message: 'AI 清理失败',
          description:
            'DeepSeek 调用异常，已保留 Jina 原始抓取内容。可点击「加载完整正文」重新触发。',
        }
      : aiStatus === 'skipped'
        ? {
            type: 'info' as const,
            message: '该篇未经 AI 清理',
            description:
              'DeepSeek 当前不可用（未配置 API Key 或账户余额不足），已保留 Jina 原始抓取内容。',
          }
        : aiStatus === 'cleaned'
          ? null
          : {
              // null OR 'not_attempted'
              type: 'warning' as const,
              message: '该篇尚未抓取正文',
              description:
                '后台调度暂未抓取本篇的完整正文，可点击下方「加载完整正文」手动触发。',
            };

  return (
    <PageShell maxWidth="full">
      {/* Header */}
      <header className="ad-detail-header">
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/news')}
          className="ad-mb-3"
        >
          返回资讯
        </Button>
        <div className="ad-detail-meta">
          <span>{data.source}</span>
          <span className="ad-detail-meta__divider">·</span>
          <span>{formatDateTime(data.published_at)}</span>
          <span className="ad-detail-meta__divider">·</span>
          <span>{data.language}</span>
          {data.author && (
            <>
              <span className="ad-detail-meta__divider">·</span>
              <span>{data.author}</span>
            </>
          )}
          <ImportanceStars level={data.importance} />
        </div>

        <h1 className="ad-detail-title">
          {data.title}
        </h1>

        <div className="ad-detail-actions">
          {symbols.length > 0 && (
            <Space size={4} wrap className="ad-detail-actions__symbols">
              {symbols.map((s) => (
                <Link
                  key={`${s.symbol}-${s.match_type ?? 'symbol'}`}
                  to={`/instruments/${encodeURIComponent(s.symbol)}`}
                >
                  <InstrumentCodeTag
                    code={s.symbol}
                    name={s.name ?? undefined}
                    name_zh={s.name_zh ?? undefined}
                  />
                </Link>
              ))}
            </Space>
          )}
          {data.event_category && (
            <Tag
              color={
                data.event_category === 'geopolitics' ||
                data.event_category === 'central_bank' ||
                data.event_category === 'election' ||
                data.event_category === 'trade_war' ||
                data.event_category === 'sanction'
                  ? ({
                      geopolitics: 'volcano',
                      central_bank: 'geekblue',
                      election: 'purple',
                      trade_war: 'red',
                      sanction: 'magenta',
                    } as const)[data.event_category]
                  : 'geekblue'
              }
              className="ad-detail-tag ad-detail-tag--category"
            >
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
            className="ad-detail-actions__cta"
          >
            查看原文
          </Button>
        </div>
      </header>

      <div className="ad-detail-grid">
        {/* Body */}
        <div>
          <article className="ad-detail-article">
            {/* AI-cleanup observability banner (M22-3). Sits above the
                body so the reader always knows whether the text they
                are about to read has been cleaned by DeepSeek. */}
            {aiBanner && (
              <Alert
                className="ad-mb-3"
                type={aiBanner.type}
                showIcon
                message={aiBanner.message}
                description={aiBanner.description}
              />
            )}
            {showTranslation ? (
              // Side-by-side view: original (left) + Chinese (right).
              // We render the original body using the same Markdown
              // pipeline as the single-column view; on the right we
              // render the LLM translation, falling back to a
              // loading/empty state while the mutation is in flight.
              <div className="news-translation-pair">
                <div className="news-translation-pair__col">
                  <div className="news-translation-pair__header">
                    <span>原文</span>
                    <span className="ad-text-small ad-text-tertiary">
                      {data.language?.toUpperCase() || 'EN'}
                    </span>
                  </div>
                  <div className="news-translation-pair__body">
                    {fullContentToRender ? (
                      <Markdown source={fullContentToRender} />
                    ) : data.body ? (
                      <div className="ad-detail-article__body">{data.body}</div>
                    ) : (
                      <EmptyState title="暂无原文" description="尚未抓到原文，可点击下方「加载完整正文」或前往原文链接" />
                    )}
                  </div>
                </div>
                <div className="news-translation-pair__col">
                  <div className="news-translation-pair__header">
                    <span>中文翻译</span>
                    <span className="ad-text-small ad-text-tertiary">
                      ZH · DeepSeek
                    </span>
                  </div>
                  <div className="news-translation-pair__body">
                    {translateArticle.isPending && !translationToShow ? (
                      <div className="ad-flex ad-flex-col ad-items-center ad-justify-center ad-py-8">
                        <Spin />
                        <div className="ad-mt-3 ad-text-small ad-text-tertiary">
                          AI 正在翻译…
                        </div>
                      </div>
                    ) : translationToShow ? (
                      <Markdown source={translationToShow} />
                    ) : (
                      <EmptyState title="翻译暂不可用" description="翻译服务暂未启用或该文章类型不支持翻译" />
                    )}
                  </div>
                </div>
              </div>
            ) : fullContentToRender ? (
              // Cache hit (from a previous click) OR we just finished
              // fetching — render the Markdown body inline.
              <Markdown source={fullContentToRender} />
            ) : data.body ? (
              <div className="ad-detail-article__body">
                {data.body}
              </div>
            ) : (
              <EmptyState title="暂无正文，请前往原文查看完整内容" description="可点击「加载完整正文」尝试抓取，或前往原文链接阅读" />
            )}

            {/* Load-full-text control: only when we don't already have
                a rendered full body. The summary that the crawler gave
                us is usually just an excerpt, so users need an explicit
                way to see the whole article. */}
            {!fullContentToRender && !showTranslation && (
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

            {fetchedAt && !showTranslation && (
              <div className="ad-mt-3 ad-text-small ad-text-muted">
                全文缓存于 {formatDateTime(fetchedAt)}
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

            {/* Translation toggle — only for English articles where the
                backend will accept the request. Non-English content
                never shows this control. */}
            {isEnglish && (
              <div className="ad-mt-4 ad-flex ad-items-center ad-gap-3 ad-flex-wrap">
                <Tooltip title="调用 DeepSeek 将正文翻译为中文（仅英文文章可用），首次调用约 5-15 秒，结果会缓存">
                  <Switch
                    checked={showTranslation}
                    onChange={handleTranslationToggle}
                    loading={translateArticle.isPending}
                    checkedChildren="译本开启"
                    unCheckedChildren="原文"
                  />
                </Tooltip>
                <span className="ad-text-small ad-text-tertiary ad-flex ad-items-center ad-gap-1">
                  <TranslationOutlined />
                  AI 译本并排显示
                </span>
                {data.translation_generated_at && (
                  <span className="ad-text-small ad-text-muted">
                    已翻译于 {formatDateTimeCompact(data.translation_generated_at)}
                    {translateArticle.data?.cached ? ' · 命中缓存' : ''}
                  </span>
                )}
              </div>
            )}

            {translateArticle.isError && (
              <Alert
                className="ad-mt-3"
                type="warning"
                showIcon
                message="翻译失败"
                description={
                  (translateArticle.error as Error | undefined)?.message ??
                  '请稍后重试'
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
                    <HelpPopover termKey="sentiment_confidence" mode={mode}>LLM 置信度</HelpPopover>
                  </span>
                  <div className="ad-sentiment-bar ad-flex-1">
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
                    <HelpPopover termKey="sentiment_drivers" mode={mode}>关键驱动</HelpPopover>
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
              <EmptyState title="散户讨论内容由 Agent E 后续接入" description="将汇总雪球、东方财富股吧、Reddit 等社区讨论" />
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
                {otherSymbols.map((s) => (
                  <Link
                    key={`${s.symbol}-${s.match_type ?? 'symbol'}`}
                    to={`/instruments/${encodeURIComponent(s.symbol)}`}
                  >
                    <InstrumentCodeTag
                      code={s.symbol}
                      name={s.name ?? undefined}
                      name_zh={s.name_zh ?? undefined}
                    />
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
              <EmptyState title="暂无相关资讯" description="未找到与本文主题、标的或行业相关的其他资讯" />
            ) : (
              <List
                className="ad-list-compact"
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
                            {formatDateTimeCompact(item.published_at)}
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
