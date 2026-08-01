import { useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Tag,
  Badge,
  Space,
  Button,
  List,
  Tooltip,
  Segmented,
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
import LoadingBlock from '@/components/LoadingBlock';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import StatCard from '@/components/StatCard';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import { formatDateTime, formatDateTimeCompact } from '@/utils/datetime';
import { SENTIMENT_COLORS, SENTIMENT_LABELS } from '@/utils/sentiment';
import { cleanNewsFullContent } from '@/utils/text';
import HelpPopover from '@/components/HelpPopover';
import { useSettingsStore } from '@/stores/settings';

const SOCIAL_SOURCES = new Set(['xueqiu', 'reddit', 'weibo']);

/**
 * Render-layer newline guard (2026-08-01 间距修复).
 * 抓取 / AI 清理 / 译文管线偶尔会在正文里留下 3+ 连续换行（HTML→文本时
 * <p>/<br> 双重换行）。Markdown 渲染器会把多余空行折叠掉，但纯文本
 * pre-wrap 兜底路径不会 —— 每个多余换行都是一整行空白。统一在渲染前
 * 把 3+ 连换行折叠成一个空行；只动渲染输入，不回写数据。
 */
function collapseBlankRuns(text: string): string {
  return text.replace(/\n{3,}/g, '\n\n');
}

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

/**
 * Normalize sentiment_score regardless of backend convention.
 * Backend stores either the `-100..+100` integer range (legacy pipeline)
 * or the `-1..+1` float range (newer pipeline). Detect by magnitude and
 * surface a uniform "-0.78" style number to the UI.
 * (review-news-analyst P0-6)
 */
function formatSentimentScore(score: number): string {
  if (!Number.isFinite(score)) return '—';
  // |x| > 2 → treat as -100..+100 scale.
  const normalized = Math.abs(score) > 2 ? score / 100 : score;
  return normalized.toFixed(2);
}

/**
 * RetailSentimentPanel — wires the existing `/news/retail-sentiment/{symbol}`
 * endpoint to the previously-static placeholder.  Reviews flagged this as
 * a permanent empty state; now it actually fetches & renders the 7-day
 * community chatter summary.
 */
function RetailSentimentPanel({ symbol }: { symbol: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['news-retail-sentiment', symbol],
    queryFn: () => newsApi.retailSentiment(symbol, '7d').then((r) => r.data),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
  });

  return (
    <Panel
      variant="default"
      title={
        <span>
          <ChatOutlined className="ad-icon-mr" />
          散户讨论
          <span className="ad-text-secondary ad-text-12 ad-ml-2">{symbol}</span>
        </span>
      }
      className="ad-mt-5"
      padding="md"
    >
      {isLoading ? (
        <LoadingBlock size="sm" />
      ) : isError || !data ? (
        <EmptyState
          title="暂未采集到散户讨论"
          description="雪球 / 东方财富股吧 / Reddit 等社区讨论将在下一轮调度后接入"
        />
      ) : (
        <div className="ad-flex ad-flex-col ad-gap-3">
          <div className="ad-flex ad-items-baseline ad-gap-3">
            <span className="ad-text-12 ad-text-secondary">整体情绪</span>
            <span className="ad-text-18 ad-font-medium">
              {formatSentimentScore(data.overall)}
            </span>
            <span className="ad-text-12 ad-text-tertiary">
              （-1.00 ~ +1.00；正值偏多）
            </span>
          </div>
          {(data.bull_bear_ratio?.bull != null || data.bull_bear_ratio?.bear != null) && (
            <div className="ad-flex ad-items-baseline ad-gap-3">
              <span className="ad-text-12 ad-text-secondary">多空比</span>
              <span className="ad-text-14 tabular-nums">
                {data.bull_bear_ratio?.bull ?? 0}
              </span>
              <span className="ad-text-12 ad-text-tertiary">vs</span>
              <span className="ad-text-14 tabular-nums">
                {data.bull_bear_ratio?.bear ?? 0}
              </span>
            </div>
          )}
          {typeof data.controversy === 'number' && (
            <div className="ad-flex ad-items-baseline ad-gap-3">
              <span className="ad-text-12 ad-text-secondary">分歧度</span>
              <span className="ad-text-14 tabular-nums">
                {data.controversy.toFixed(2)}
              </span>
              <span className="ad-text-12 ad-text-tertiary">（0=一致，1=分歧）</span>
            </div>
          )}
          {data.main_themes && data.main_themes.length > 0 && (
            <div className="ad-flex ad-flex-wrap ad-gap-1">
              <span className="ad-text-12 ad-text-secondary">主题</span>
              {data.main_themes.slice(0, 5).map((t, i) => (
                <Tag key={i}>{t.theme}</Tag>
              ))}
            </div>
          )}
          {data.summary && (
            <div className="ad-text-13 ad-text-secondary">
              {data.summary}
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

export default function NewsDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const articleId = Number(id);
  const queryClient = useQueryClient();
  const mode = useSettingsStore((s) => s?.mode ?? 'novice');

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

  // AI translation view (reworked 2026-07-26). Non-Chinese articles are
  // auto-translated at ingestion (title → ``title_zh``, body →
  // ``translated_zh``); the detail page defaults to the Chinese
  // rendering and offers a full-article 中文/原文 switch. The manual
  // translate mutation remains as a fallback for rows the pipeline
  // hasn't reached yet (older articles, LLM hiccups).
  const [viewMode, setViewMode] = useState<'zh' | 'original'>('zh');
  const [translationOverride, setTranslationOverride] = useState<string | null>(
    null,
  );
  const CHINESE_LANGS = useMemo(
    () => new Set(['zh', 'cn', 'zh-cn', 'zh-hans', 'zh-hant', 'zh-tw', 'zh-hk']),
    [],
  );
  const isNonChinese = !CHINESE_LANGS.has((data?.language || '').toLowerCase());

  // Reset the view + override when navigating between articles so a
  // fresh article doesn't inherit the previous one's translation.
  useEffect(() => {
    setViewMode('zh');
    setTranslationOverride(null);
  }, [articleId]);

  const translateArticle = useMutation({
    mutationFn: (): Promise<NewsTranslateResponse> =>
      newsApi.translate(articleId).then((r) => r.data),
    onSuccess: (resp) => {
      setTranslationOverride(resp.translation);
      setViewMode('zh');
      // Refresh the article detail so a subsequent mount picks up the
      // cached translation (and the freshly-filled title_zh) without an
      // extra round-trip.
      queryClient.invalidateQueries({ queryKey: ['news-detail', articleId] });
    },
  });

  const translationFromServer = data?.translated_zh ?? null;
  const translationToShow = translationOverride ?? translationFromServer;
  // Chinese view needs BOTH intent (viewMode) and content. When the
  // pipeline hasn't translated this row yet we keep showing the
  // original body with a slim "翻译进行中" notice — never an empty pane.
  const showChinese = viewMode === 'zh' && !!translationToShow;

  // Update document title for nicer browser tab (Chinese-first).
  useEffect(() => {
    const tabTitle = data?.title_zh ?? data?.title;
    if (tabTitle) {
      document.title = `${tabTitle} - 资讯`;
    }
    return () => {
      document.title = '投研平台';
    };
  }, [data?.title, data?.title_zh]);

  // Defence-layer cleanup: strip DeepSeek-style  thinking blocks and
  // repeated title lines before we render the Markdown body.
  // NOTE: this useMemo must be declared before any early return so the
  // hook count is identical across loading and loaded renders.
  const fullContentToRender = renderedFullContent ?? data?.full_content;
  const cleanedFullContent = useMemo(
    () => (fullContentToRender && data?.title ? collapseBlankRuns(cleanNewsFullContent(fullContentToRender, data.title)) : null),
    [fullContentToRender, data?.title],
  );

  if (isLoading) {
    return (
      <PageShell maxWidth="full">
        <div className="ad-p-15 ad-text-center">
          <LoadingBlock size="lg" />
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
          message: '原文提取失败',
          description:
            'Jina Reader 未能从该页提取出可用的正文（通常因网站正文为空或被反爬拦截），已保留文章摘要。可点击「加载完整正文」重新触发。',
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
    <PageShell maxWidth="full" className="news-detail">
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
          {showChinese ? (data.title_zh ?? data.title) : data.title}
        </h1>
        {/* Original-title subtitle: when the Chinese rendering leads,
            keep the source title one glance away — quieter, smaller,
            so it reads as provenance rather than a second headline. */}
        {showChinese && data.title_zh && data.title_zh !== data.title && (
          <div className="ad-detail-title__original">{data.title}</div>
        )}

        <div className="ad-detail-actions">
          {symbols.length > 0 && (
            <Space size="small" wrap className="ad-detail-actions__symbols">
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
                    ` · ${formatSentimentScore(data.sentiment_score)}`}
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
            {/* Language toolbar (2026-07-26): full-article 中文/原文
                switch for non-Chinese sources. The body defaults to the
                AI translation produced at ingestion; 原文 is always one
                tap away. Sits directly above the body it controls. */}
            {isNonChinese && (
              <div className="news-lang-toolbar">
                <Segmented
                  value={viewMode}
                  onChange={(v) => setViewMode(v as 'zh' | 'original')}
                  options={[
                    { label: '中文译文', value: 'zh' },
                    { label: `${(data.language || 'en').toUpperCase()} 原文`, value: 'original' },
                  ]}
                />
                <span className="news-lang-toolbar__meta">
                  <TranslationOutlined />
                  {data.translation_generated_at
                    ? `AI 翻译 · ${formatDateTimeCompact(data.translation_generated_at)}`
                    : 'AI 翻译'}
                </span>
              </div>
            )}

            {/* Translation-pending notice: the user asked for Chinese
                (default) but the pipeline hasn't produced one yet. Keep
                the original body visible underneath — never an empty
                pane — and offer a manual trigger as the escape hatch. */}
            {isNonChinese && viewMode === 'zh' && !translationToShow && (
              <div className="news-translation-notice">
                {translateArticle.isPending ? (
                  <>
                    <LoadingBlock size="sm" />
                    <span>AI 正在翻译，请稍候…</span>
                  </>
                ) : (
                  <>
                    <span className="news-translation-notice__text">
                      中文译文尚未就绪，后台翻译中（通常入库后几分钟内完成）
                    </span>
                    <Button
                      size="small"
                      type="link"
                      onClick={() => translateArticle.mutate()}
                    >
                      立即翻译
                    </Button>
                  </>
                )}
              </div>
            )}

            {showChinese ? (
              // Chinese rendering: the ingestion-time AI translation
              // (Markdown, same pipeline as the original body).
              // P4 内容轨：prose-reading 承载 editorial 阅读尺度（theme.css）。
              <div className="prose-reading news-detail__reading">
                <Markdown source={collapseBlankRuns(translationToShow!)} />
              </div>
            ) : cleanedFullContent ? (
              // Cache hit (from a previous click) OR we just finished
              // fetching — render the cleaned Markdown body inline.
              <div className="prose-reading news-detail__reading">
                <Markdown source={cleanedFullContent} />
              </div>
            ) : data.body ? (
              <div className="ad-detail-article__body prose-reading news-detail__reading">
                {collapseBlankRuns(data.body)}
              </div>
            ) : (
              <EmptyState title="暂无正文，请前往原文查看完整内容" description="可点击「加载完整正文」尝试抓取，或前往原文链接阅读" />
            )}

            {/* Load-full-text control: only when we don't already have
                a rendered full body. The summary that the crawler gave
                us is usually just an excerpt, so users need an explicit
                way to see the whole article. Irrelevant in the Chinese
                view — the translation already covers the body. */}
            {!fullContentToRender && !showChinese && (
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

            {fetchedAt && !showChinese && (
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

          {/* Social discussion (xueqiu/reddit retail sentiment).
              Wires the existing backend endpoint instead of showing a
              permanent placeholder (see review-news-analyst P0-4). */}
          {showSocial && primarySymbol && (
            <RetailSentimentPanel symbol={primarySymbol} />
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
              />
              <StatCard
                title="评论"
                value={formatBigNumber(data.engagement?.comments)}
                icon={<MessageOutlined />}
              />
              <StatCard
                title="转发"
                value={formatBigNumber(data.engagement?.shares)}
                icon={<ShareAltOutlined />}
              />
              <StatCard
                title="阅读"
                value={formatBigNumber(data.engagement?.views)}
                icon={<EyeOutlined />}
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
              <LoadingBlock size="md" />
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
