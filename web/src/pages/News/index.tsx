import { useState, useMemo, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import {
  Input,
  Segmented,
  Select,
  DatePicker,
  Tag,
  Badge,
  Space,
  Spin,
  Empty,
  Skeleton,
  Tooltip,
  message,
} from 'antd';
import {
  SearchOutlined,
  StarFilled,
  StarOutlined,
  LinkOutlined,
  LikeOutlined,
  MessageOutlined,
  ShareAltOutlined,
  EyeOutlined,
  FireOutlined,
} from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import { newsApi } from '@/api/news';
import type {
  NewsArticle,
  NewsMarket,
  NewsWatchlistResponse,
  SentimentLabel,
  ImportanceLevel,
} from '@/types/news';
import Panel from '@/components/Panel';

const { RangePicker } = DatePicker;

const PAGE_SIZE = 20;

const MARKET_OPTIONS: { label: string; value: NewsMarket | 'all' }[] = [
  { label: '全部', value: 'all' },
  { label: 'A 股', value: 'cn_a' },
  { label: '美股', value: 'us' },
  { label: '加密', value: 'crypto' },
];

const MARKET_BADGE: Record<NewsMarket, { color: string; label: string }> = {
  cn_a: { color: 'magenta', label: 'A 股' },
  us: { color: 'blue', label: '美股' },
  crypto: { color: 'gold', label: '加密' },
};

const SOURCE_LABELS: Record<string, { emoji: string; label: string }> = {
  xinhua: { emoji: '📰', label: '新华' },
  sina: { emoji: '📰', label: '新浪财经' },
  eastmoney: { emoji: '📊', label: '东方财富' },
  cls: { emoji: '⚡', label: '财联社' },
  xueqiu: { emoji: '📈', label: '雪球' },
  reddit: { emoji: '🦍', label: 'Reddit' },
  coindesk: { emoji: '🪙', label: 'CoinDesk' },
  cointelegraph: { emoji: '🪙', label: 'Cointelegraph' },
  bloomberg: { emoji: '🏛', label: 'Bloomberg' },
  reuters: { emoji: '🏛', label: '路透' },
};

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

/** Build ISO date for `dayjs()` value. */
function toIso(d: Dayjs | null | undefined, endOfDay = false): string | undefined {
  if (!d) return undefined;
  return (endOfDay ? d.endOf('day') : d.startOf('day')).toISOString();
}

/** Approximate "x 分钟前" / "x 小时前" formatter. */
function formatRelative(iso: string): string {
  const t = dayjs(iso);
  if (!t.isValid()) return '';
  const diff = dayjs().diff(t, 'minute');
  if (diff < 1) return '刚刚';
  if (diff < 60) return `${diff} 分钟前`;
  const h = Math.floor(diff / 60);
  if (h < 24) return `${h} 小时前`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d} 天前`;
  return t.format('YYYY-MM-DD');
}

/** Render a 1..5 star row. */
function ImportanceStars({ level }: { level: ImportanceLevel | null }) {
  if (!level) return null;
  const filled = Math.max(0, Math.min(5, level));
  return (
    <Tooltip title={`重要性 ${level}/5`}>
      <span style={{ fontSize: 11, letterSpacing: 1, color: 'var(--text-tertiary)' }}>
        {Array.from({ length: 5 }).map((_, i) => (
          <StarFilled
            key={i}
            style={{
              color: i < filled ? IMPORTANCE_COLOR : 'var(--text-muted)',
              opacity: i < filled ? 1 : 0.4,
              fontSize: 11,
              marginRight: 1,
            }}
          />
        ))}
      </span>
    </Tooltip>
  );
}

/** Single article card in the feed. */
function NewsCard({
  article,
  onOpen,
  onPickSymbol,
  sourceOptions,
}: {
  article: NewsArticle;
  onOpen: (a: NewsArticle) => void;
  onPickSymbol: (sym: string) => void;
  sourceOptions: { value: string; label: string }[];
}) {
  const source = SOURCE_LABELS[article.source] ?? {
    emoji: '🔗',
    label: sourceOptions.find((s) => s.value === article.source)?.label ?? article.source,
  };
  const market = MARKET_BADGE[article.market];
  const sentiment = article.sentiment_label;

  return (
    <div
      style={{
        padding: 'var(--space-4) var(--space-5)',
        borderBottom: '1px solid var(--border-default)',
        cursor: 'pointer',
        transition: 'background var(--transition-fast)',
      }}
      onClick={() => onOpen(article)}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = 'var(--bg-hover)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = 'transparent';
      }}
    >
      {/* Row 1: source · market · time · importance */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-3)',
          fontSize: 12,
          color: 'var(--text-tertiary)',
          marginBottom: 8,
        }}
      >
        <span>{source.emoji} {source.label}</span>
        <span style={{ color: 'var(--text-muted)' }}>·</span>
        {market && <Tag color={market.color} style={{ margin: 0, fontSize: 11 }}>{market.label}</Tag>}
        {article.event_category && (
          <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{article.event_category}</span>
        )}
        <span style={{ flex: 1 }} />
        <Tooltip title={dayjs(article.published_at).format('YYYY-MM-DD HH:mm:ss')}>
          <span>{formatRelative(article.published_at)}</span>
        </Tooltip>
        <ImportanceStars level={article.importance} />
      </div>

      {/* Title */}
      <div
        style={{
          fontSize: 15,
          fontWeight: 500,
          color: 'var(--text-primary)',
          lineHeight: 1.5,
          marginBottom: 8,
          letterSpacing: '-0.01em',
        }}
      >
        {article.title}
      </div>

      {/* Body preview */}
      {article.body && (
        <div
          style={{
            fontSize: 13,
            color: 'var(--text-secondary)',
            lineHeight: 1.6,
            marginBottom: 10,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {article.body}
        </div>
      )}

      {/* Row 3: symbols + sentiment + engagement */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <Space size={4} wrap>
          {article.symbols.slice(0, 6).map((s) => (
            <Tag
              key={`${s.symbol}-${s.match_type}`}
              color="default"
              style={{
                margin: 0,
                fontSize: 11,
                cursor: 'pointer',
                borderColor: 'var(--card-border)',
              }}
              onClick={(e) => {
                e.stopPropagation();
                onPickSymbol(s.symbol);
              }}
            >
              {s.symbol}
            </Tag>
          ))}
        </Space>

        <span style={{ flex: 1 }} />

        {sentiment && (
          <Tooltip
            title={
              article.sentiment_score != null
                ? `分数 ${article.sentiment_score.toFixed(2)} · 置信度 ${(
                    (article.sentiment_confidence ?? 0) * 100
                  ).toFixed(0)}%`
                : SENTIMENT_LABELS[sentiment]
            }
          >
            <Badge
              color={SENTIMENT_COLORS[sentiment]}
              text={
                <span
                  style={{
                    color: SENTIMENT_COLORS[sentiment],
                    fontSize: 12,
                    fontWeight: 500,
                  }}
                >
                  {SENTIMENT_LABELS[sentiment]}
                </span>
              }
            />
          </Tooltip>
        )}

        {article.engagement?.likes != null && (
          <span style={engagementStyle}>
            <LikeOutlined /> {formatBigNumber(article.engagement.likes)}
          </span>
        )}
        {article.engagement?.comments != null && (
          <span style={engagementStyle}>
            <MessageOutlined /> {formatBigNumber(article.engagement.comments)}
          </span>
        )}
        {article.engagement?.shares != null && (
          <span style={engagementStyle}>
            <ShareAltOutlined /> {formatBigNumber(article.engagement.shares)}
          </span>
        )}
        {article.engagement?.views != null && (
          <span style={engagementStyle}>
            <EyeOutlined /> {formatBigNumber(article.engagement.views)}
          </span>
        )}
      </div>
    </div>
  );
}

const engagementStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-tertiary)',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 3,
};

function formatBigNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

/** Right column: per-symbol retail sentiment ranking. */
function HotSymbolSidebar({
  data,
  loading,
  onPickSymbol,
}: {
  data: { symbol: string; label: SentimentLabel | null; score: number | null; count: number }[];
  loading: boolean;
  onPickSymbol: (sym: string) => void;
}) {
  return (
    <Panel
      variant="minimal"
      title={
        <span>
          <FireOutlined style={{ marginRight: 6, color: 'var(--accent)' }} />
          热门情绪标的
        </span>
      }
      padding="md"
    >
      {loading ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : data.length === 0 ? (
        <Empty description="暂无情绪数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <div>
          {data.map((row) => {
            const tone = row.label
              ? SENTIMENT_COLORS[row.label]
              : 'var(--text-tertiary)';
            return (
              <div
                key={row.symbol}
                onClick={() => onPickSymbol(row.symbol)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 'var(--space-3)',
                  padding: '8px 0',
                  borderBottom: '1px solid var(--border-default)',
                  cursor: 'pointer',
                  transition: 'background var(--transition-fast)',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'var(--bg-hover)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'transparent';
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 500,
                      color: 'var(--text-primary)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {row.symbol}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2 }}>
                    {row.count} 篇资讯
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: tone, fontFamily: 'var(--font-mono)' }}>
                    {row.score != null ? row.score.toFixed(2) : '—'}
                  </div>
                  <div style={{ fontSize: 11, color: tone }}>
                    {row.label ? SENTIMENT_LABELS[row.label] : '—'}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}

export default function NewsFeed() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [market, setMarket] = useState<NewsMarket | 'all'>(
    (searchParams.get('market') as NewsMarket | 'all' | null) ?? 'all'
  );
  const [source, setSource] = useState<string | undefined>(searchParams.get('source') ?? undefined);
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [searchInput, setSearchInput] = useState<string>(searchParams.get('q') ?? '');
  const [activeSymbol, setActiveSymbol] = useState<string | undefined>(
    searchParams.get('symbol') ?? undefined
  );
  // ``watchlist=1`` scopes the feed to the current user's favorites.
  // When on, the page routes through ``/news/watchlist`` instead of
  // ``/news`` so cache stays separate.
  const [watchlistMode, setWatchlistMode] = useState<boolean>(
    searchParams.get('watchlist') === '1'
  );

  // Sync URL params when filters change.
  useEffect(() => {
    const next: Record<string, string> = {};
    if (market !== 'all') next.market = market;
    if (source) next.source = source;
    if (activeSymbol) next.symbol = activeSymbol;
    if (searchInput) next.q = searchInput;
    if (watchlistMode) next.watchlist = '1';
    setSearchParams(next, { replace: true });
  }, [market, source, activeSymbol, searchInput, watchlistMode, setSearchParams]);

  // Source list for the dropdown.
  const { data: sourceStats, isLoading: sourceStatsLoading } = useQuery({
    queryKey: ['news-source-stats'],
    queryFn: () => newsApi.sourceStats().then((r) => r.data),
    staleTime: 5 * 60_000,
  });

  const sourceOptions = useMemo(() => {
    const stats = sourceStats ?? [];
    return stats.map((s: { source: string; count: number; last_24h: number }) => ({
      value: s.source,
      label: `${SOURCE_LABELS[s.source]?.label ?? s.source} (${s.count})`,
    }));
  }, [sourceStats]);

  // Article list with infinite scroll.
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
    isError,
  } = useInfiniteQuery({
    // Distinct query keys so the watchlist and global feeds do not
    // share a cache entry — the watchlist result set changes the
    // moment the user adds/removes a favorite.
    queryKey: watchlistMode
      ? ['news-watchlist', market, source, dateRange]
      : ['news-list', market, source, dateRange, activeSymbol, searchInput],
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      watchlistMode
        ? newsApi
            .watchlist({
              market: market === 'all' ? undefined : market,
              source,
              from_date: toIso(dateRange?.[0] ?? null, false),
              to_date: toIso(dateRange?.[1] ?? null, true),
              page: pageParam,
              page_size: PAGE_SIZE,
            })
            .then((r) => r.data)
        : newsApi
            .list({
              market: market === 'all' ? undefined : market,
              symbol: activeSymbol,
              source,
              from_date: toIso(dateRange?.[0] ?? null, false),
              to_date: toIso(dateRange?.[1] ?? null, true),
              q: searchInput || undefined,
              page: pageParam,
              page_size: PAGE_SIZE,
            })
            .then((r) => r.data),
    getNextPageParam: (last) =>
      last.page * last.page_size < last.total ? last.page + 1 : undefined,
  });

  // Watchlist metadata is only meaningful while watchlistMode is on.
  // We pull it out of the most recent page; if no pages have loaded
  // yet (initial load), the response falls back to undefined.
  const watchlistMeta = useMemo(() => {
    if (!watchlistMode) return null;
    const last = data?.pages?.[data.pages.length - 1] as
      | (NewsWatchlistResponse | undefined)
      | undefined;
    return last?.watchlist ?? null;
  }, [data, watchlistMode]);

  // Infinite-scroll via IntersectionObserver.
  const sentinelRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (!node) return;
      const obs = new IntersectionObserver(
        (entries) => {
          if (entries[0]?.isIntersecting && hasNextPage && !isFetchingNextPage) {
            fetchNextPage();
          }
        },
        { rootMargin: '200px' }
      );
      obs.observe(node);
      return () => obs.disconnect();
    },
    [hasNextPage, isFetchingNextPage, fetchNextPage]
  );

  const articles = useMemo(() => {
    return (data?.pages ?? []).flatMap((p) => p.items);
  }, [data]);

  // Aggregate top-10 symbols by importance-weighted sentiment for sidebar.
  const hotSymbols = useMemo(() => {
    const bucket = new Map<
      string,
      { count: number; weighted: number; scoreSum: number; positive: number; negative: number; neutral: number }
    >();
    for (const a of articles) {
      for (const s of a.symbols) {
        const cur = bucket.get(s.symbol) ?? {
          count: 0,
          weighted: 0,
          scoreSum: 0,
          positive: 0,
          negative: 0,
          neutral: 0,
        };
        cur.count += 1;
        const w = a.importance ?? 3;
        cur.weighted += w;
        if (a.sentiment_score != null) cur.scoreSum += a.sentiment_score * w;
        if (a.sentiment_label === 'positive') cur.positive += 1;
        else if (a.sentiment_label === 'negative') cur.negative += 1;
        else cur.neutral += 1;
        bucket.set(s.symbol, cur);
      }
    }
    return Array.from(bucket.entries())
      .map(([symbol, v]) => {
        const score = v.weighted > 0 ? v.scoreSum / v.weighted : null;
        let label: SentimentLabel | null = null;
        if (score != null) {
          if (score > 0.2) label = 'positive';
          else if (score < -0.2) label = 'negative';
          else label = 'neutral';
        }
        return { symbol, count: v.count, score, label };
      })
      .filter((r) => r.count > 0)
      .sort((a, b) => b.count - a.count)
      .slice(0, 10);
  }, [articles]);

  const handleOpen = (a: NewsArticle) => {
    navigate(`/news/${a.id}`);
  };

  const handlePickSymbol = (sym: string) => {
    setActiveSymbol(sym);
    message.info(`已筛选标的: ${sym}`);
  };

  return (
    <div>
      <h1
        style={{
          fontSize: 'var(--text-h1-size)',
          fontWeight: 500,
          color: 'var(--text-primary)',
          margin: '0 0 8px',
          letterSpacing: '-0.03em',
        }}
      >
        资讯
      </h1>
      <p
        style={{
          margin: '0 0 24px',
          color: 'var(--text-tertiary)',
          fontSize: 'var(--text-body-size)',
        }}
      >
        多市场新闻聚合 · 情绪与重要性实时标注
      </p>

      {/* Filter bar */}
      <div
        style={{
          background: 'var(--card-bg)',
          border: '1px solid var(--card-border)',
          borderRadius: 'var(--card-radius)',
          padding: 'var(--space-4) var(--space-5)',
          marginBottom: 20,
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        <div
          style={{
            display: 'flex',
            gap: 12,
            flexWrap: 'wrap',
            alignItems: 'center',
          }}
        >
          <Tag.CheckableTag
            checked={watchlistMode}
            onChange={(checked) => {
              setWatchlistMode(checked);
              if (checked) {
                // Switching to the watchlist feed means the per-symbol
                // tag and search no longer apply — clear them so the
                // user does not see a chip pinned to a symbol that is
                // no longer in scope.
                setActiveSymbol(undefined);
              }
            }}
            style={{
              padding: '4px 12px',
              borderRadius: 16,
              border: '1px solid var(--card-border)',
              background: watchlistMode ? 'var(--accent-soft, rgba(82,196,26,0.12))' : 'transparent',
              color: watchlistMode ? 'var(--accent)' : 'var(--text-secondary)',
              fontSize: 13,
              fontWeight: watchlistMode ? 500 : 400,
              cursor: 'pointer',
              userSelect: 'none',
            }}
          >
            <StarFilled style={{ marginRight: 4, fontSize: 11 }} />
            我的自选
          </Tag.CheckableTag>
          <Segmented
            value={market}
            onChange={(v) => setMarket(v as NewsMarket | 'all')}
            options={MARKET_OPTIONS}
          />
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索标题/正文…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            style={{ width: 240 }}
          />
          <Select
            allowClear
            placeholder="来源"
            loading={sourceStatsLoading}
            value={source}
            onChange={(v) => setSource(v)}
            options={sourceOptions}
            style={{ minWidth: 180 }}
          />
          <RangePicker
            value={dateRange}
            onChange={(v) => setDateRange(v as [Dayjs | null, Dayjs | null] | null)}
            allowEmpty={[true, true]}
          />
          {activeSymbol && (
            <Tag
              closable
              onClose={() => setActiveSymbol(undefined)}
              color="accent"
              style={{ margin: 0 }}
            >
              标的: {activeSymbol}
            </Tag>
          )}
          <div style={{ flex: 1 }} />
          {watchlistMode && watchlistMeta ? (
            <Tooltip title="关联到当前用户自选标的的资讯（按自选/池内 ETF 代码匹配）">
              <span
                style={{
                  fontSize: 12,
                  color: 'var(--text-tertiary)',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                自选标的 {watchlistMeta.symbols.length} 个 · 相关资讯 {watchlistMeta.total_articles} 条
              </span>
            </Tooltip>
          ) : (
            <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
              共 {data?.pages?.[0]?.total ?? 0} 条
            </span>
          )}
        </div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) 320px',
          gap: 'var(--space-5)',
        }}
      >
        {/* Feed */}
        <div
          style={{
            background: 'var(--card-bg)',
            border: '1px solid var(--card-border)',
            borderRadius: 'var(--card-radius)',
            overflow: 'hidden',
          }}
        >
          {isError ? (
            <Empty
              description="加载失败，请稍后重试"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              style={{ padding: 40 }}
            />
          ) : isLoading ? (
            <div style={{ padding: 20 }}>
              <Skeleton active paragraph={{ rows: 6 }} />
            </div>
          ) : articles.length === 0 ? (
            <Empty description="暂无符合筛选条件的资讯" style={{ padding: 60 }} />
          ) : (
            <>
              {articles.map((a) => (
                <NewsCard
                  key={a.id}
                  article={a}
                  onOpen={handleOpen}
                  onPickSymbol={handlePickSymbol}
                  sourceOptions={sourceOptions}
                />
              ))}
              <div
                ref={sentinelRef}
                style={{ padding: 20, textAlign: 'center', color: 'var(--text-tertiary)' }}
              >
                {isFetchingNextPage ? (
                  <Spin />
                ) : hasNextPage ? (
                  '加载更多…'
                ) : (
                  <span style={{ fontSize: 12 }}>— 已加载全部 —</span>
                )}
              </div>
            </>
          )}
        </div>

        {/* Sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <HotSymbolSidebar
            data={hotSymbols}
            loading={isLoading}
            onPickSymbol={handlePickSymbol}
          />
          <Panel variant="minimal" title="情绪图例" padding="md">
            <Space direction="vertical" size={6}>
              {(['positive', 'neutral', 'negative'] as SentimentLabel[]).map((l) => (
                <div key={l} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Badge color={SENTIMENT_COLORS[l]} />
                  <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                    {SENTIMENT_LABELS[l]} ({(l === 'positive' && '绿') || (l === 'neutral' && '灰') || '红'})
                  </span>
                </div>
              ))}
              <div
                style={{
                  marginTop: 8,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  fontSize: 12,
                  color: 'var(--text-tertiary)',
                }}
              >
                <StarOutlined style={{ color: IMPORTANCE_COLOR }} /> 重要性 1-5
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: 'var(--text-tertiary)',
                  marginTop: 4,
                }}
              >
                <LinkOutlined style={{ marginRight: 4 }} />
                点击标的 chip 自动筛选
              </div>
            </Space>
          </Panel>
        </div>
      </div>
    </div>
  );
}
