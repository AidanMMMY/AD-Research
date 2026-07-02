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
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import Panel from '@/components/Panel';
import EmptyState from '@/components/EmptyState';

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
      <span className="ad-text-small ad-text-tertiary ad-letter-spacing">
        {Array.from({ length: 5 }).map((_, i) => (
          <StarFilled
            key={i}
            className="ad-text-xs ad-mr-1"
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
      className="ad-news-card"
      onClick={() => onOpen(article)}
    >
      {/* Row 1: source · market · time · importance */}
      <div className="ad-news-card__meta">
        <span>{source.emoji} {source.label}</span>
        <span className="ad-text-muted">·</span>
        {market && <Tag color={market.color} className="ad-detail-tag">{market.label}</Tag>}
        {article.event_category && (
          <span className="ad-text-small ad-text-tertiary">{article.event_category}</span>
        )}
        <span className="ad-flex-1" />
        <Tooltip title={dayjs(article.published_at).format('YYYY-MM-DD HH:mm:ss')}>
          <span>{formatRelative(article.published_at)}</span>
        </Tooltip>
        <ImportanceStars level={article.importance} />
      </div>

      {/* Title */}
      <div className="ad-news-card__title">
        {article.title}
      </div>

      {/* Body preview */}
      {article.body && (
        <div className="ad-news-card__body">
          {article.body}
        </div>
      )}

      {/* Row 3: symbols + sentiment + engagement */}
      <div className="ad-news-card__footer">
        <Space size={4} wrap>
          {article.symbols.slice(0, 6).map((s) => (
            <Tag
              key={`${s.symbol}-${s.match_type}`}
              color="default"
              className="ad-mr-1 ad-chip-tag"
              onClick={(e) => {
                e.stopPropagation();
                onPickSymbol(s.symbol);
              }}
            >
              {s.symbol}
            </Tag>
          ))}
        </Space>

        <span className="ad-flex-1" />

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
                  className="ad-sentiment-label"
                  style={{ color: SENTIMENT_COLORS[sentiment] }}
                >
                  {SENTIMENT_LABELS[sentiment]}
                </span>
              }
            />
          </Tooltip>
        )}

        {article.engagement?.likes != null && (
          <span className="ad-news-card__engagement">
            <LikeOutlined /> {formatBigNumber(article.engagement.likes)}
          </span>
        )}
        {article.engagement?.comments != null && (
          <span className="ad-news-card__engagement">
            <MessageOutlined /> {formatBigNumber(article.engagement.comments)}
          </span>
        )}
        {article.engagement?.shares != null && (
          <span className="ad-news-card__engagement">
            <ShareAltOutlined /> {formatBigNumber(article.engagement.shares)}
          </span>
        )}
        {article.engagement?.views != null && (
          <span className="ad-news-card__engagement">
            <EyeOutlined /> {formatBigNumber(article.engagement.views)}
          </span>
        )}
      </div>
    </div>
  );
}

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
      variant="default"
      title={
        <span>
          <FireOutlined className="ad-icon-accent" />
          热门情绪标的
        </span>
      }
      padding="md"
    >
      {loading ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : data.length === 0 ? (
        <EmptyState title="暂无情绪数据" />
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
                className="ad-mover-row"
              >
                <div className="ad-flex-1 ad-min-w-0">
                  <div className="ad-font-medium ad-text-primary ad-truncate">
                    {row.symbol}
                  </div>
                  <div className="ad-text-small ad-text-tertiary ad-mt-2">
                    {row.count} 篇资讯
                  </div>
                </div>
                <div className="ad-text-right">
                  <div
                    className="ad-font-semibold font-mono"
                    style={{ color: tone }}
                  >
                    {row.score != null ? row.score.toFixed(2) : '—'}
                  </div>
                  <div className="ad-text-small" style={{ color: tone }}>
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

  const totalLabel = watchlistMode && watchlistMeta
    ? `自选标的 ${watchlistMeta.symbols.length} 个 · 相关资讯 ${watchlistMeta.total_articles} 条`
    : `共 ${data?.pages?.[0]?.total ?? 0} 条`;

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        title="资讯"
        description="多市场新闻聚合 · 情绪与重要性实时标注"
      />

      <FilterToolbar total={totalLabel}>
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
          className={`ad-status-chip ${watchlistMode ? 'ad-status-chip--active' : ''}`}
        >
          <StarFilled className="ad-mr-1 ad-text-xs" />
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
          >
            标的: {activeSymbol}
          </Tag>
        )}
      </FilterToolbar>

      <div className="ad-news-layout">
        {/* Feed */}
        <div className="ad-news-feed">
          {isError ? (
            <EmptyState title="加载失败，请稍后重试" />
          ) : isLoading ? (
            <div className="ad-p-5">
              <Skeleton active paragraph={{ rows: 6 }} />
            </div>
          ) : articles.length === 0 ? (
            <EmptyState title="暂无符合筛选条件的资讯" />
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
                className="ad-news-sentinel"
              >
                {isFetchingNextPage ? (
                  <Spin />
                ) : hasNextPage ? (
                  '加载更多…'
                ) : (
                  <span className="ad-text-small">— 已加载全部 —</span>
                )}
              </div>
            </>
          )}
        </div>

        {/* Sidebar */}
        <div className="dashboard-side-stack">
          <HotSymbolSidebar
            data={hotSymbols}
            loading={isLoading}
            onPickSymbol={handlePickSymbol}
          />
          <Panel variant="default" title="情绪图例" padding="md">
            <Space direction="vertical" size={6}>
              {(['positive', 'neutral', 'negative'] as SentimentLabel[]).map((l) => (
                <div key={l} className="ad-flex ad-items-center ad-gap-2">
                  <Badge color={SENTIMENT_COLORS[l]} />
                  <span className="ad-text-small ad-text-secondary">
                    {SENTIMENT_LABELS[l]} ({(l === 'positive' && '绿') || (l === 'neutral' && '灰') || '红'})
                  </span>
                </div>
              ))}
              <div className="ad-flex ad-items-center ad-gap-1 ad-mt-2 ad-text-small ad-text-tertiary">
                <StarOutlined className="ad-icon-warning" /> 重要性 1-5
              </div>
              <div className="ad-text-small ad-text-tertiary ad-mt-2">
                <LinkOutlined className="ad-mr-1" />
                点击标的 chip 自动筛选
              </div>
            </Space>
          </Panel>
        </div>
      </div>
    </PageShell>
  );
}
