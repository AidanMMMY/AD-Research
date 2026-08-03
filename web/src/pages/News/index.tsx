import './styles.css';
import { SENTIMENT_COLORS, SENTIMENT_LABELS } from '@/utils/sentiment';
import { useState, useMemo, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
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
  Button,
  message,
} from 'antd';
import {
  SearchOutlined,
  StarFilled,
  StarOutlined,
  LinkOutlined,
  FireOutlined,
} from '@ant-design/icons';
import { type Dayjs } from 'dayjs';
import { newsApi } from '@/api/news';
import type {
  NewsArticle,
  NewsMarket,
  NewsWatchlistResponse,
  SentimentLabel,
} from '@/types/news';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import { FilterSheetButton } from '@/components/BottomSheet';
import Panel from '@/components/Panel';
import EmptyState from '@/components/EmptyState';
import NewsCard, { SOURCE_LABELS } from '@/components/NewsCard';
import NewsDetailDrawer from '@/components/NewsDetailDrawer';
import LoadingBlock from '@/components/LoadingBlock';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import { useDebounce } from '@/hooks/useDebounce';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { useSettingsStore } from '@/stores/settings';

/**
 * Apple Design fixes scoped to this page (page styles.css is owned by
 * another workstream):
 * 1. Pointer-down feedback — the political/macro filter chips are
 *    antd CheckableTags, which are not covered by the global
 *    `.ad-status-chip:active` press rule; they now press (subtle
 *    scale) on touch-down, per Apple's Response principle.
 * 2. Reduced-motion users get no transform/transition at all.
 *
 * The article-card press rule and the drawer body rule moved with the
 * extracted shared components (``components/NewsCard.css`` /
 * ``components/NewsDetailDrawer.css``, 2026-08-02).
 */
const NEWS_PAGE_STYLE = `
/* Pointer-down press for the political / macro filter chips
   (Response principle). */
.news-political-chip {
  transform-origin: center;
  transition: transform var(--transition-spring-fast, 200ms var(--ease-spring)),
    background var(--transition-spring-fast, 200ms var(--ease-spring)),
    border-color var(--transition-spring-fast, 200ms var(--ease-spring));
}
.news-political-chip:active {
  transform: scale(var(--press-scale, 0.97));
}
@media (prefers-reduced-motion: reduce) {
  .news-political-chip {
    transition: none;
    transform: none;
  }
}
`;

const { RangePicker } = DatePicker;

const PAGE_SIZE = 20;

const MARKET_OPTIONS: { label: string; value: NewsMarket | 'all' }[] = [
  { label: '全部', value: 'all' },
  { label: 'A 股', value: 'cn_a' },
  { label: '美股', value: 'us' },
  { label: '加密', value: 'crypto' },
  // M22-2 (2026-07-04): "全球" is a frontend sentinel that the
  // backend maps to the union of concrete markets (``cn_a`` / ``us``
  // / ``crypto`` plus any legacy bucket the collector has written).
  // When picked we also pre-light the political-category chips via
  // ``GLOBAL_DEFAULT_CATEGORIES``.
  { label: '全球', value: 'global' },
];

/**
 * Categories the ``global`` market sentinel defaults the chip strip
 * to. Mirrors the political / macro buckets added in K12 so the user
 * lands on the most useful filter set without typing.
 */
const GLOBAL_DEFAULT_CATEGORIES: string[] = [
  'geopolitics',
  'central_bank',
  'election',
  'trade_war',
  'sanction',
];

/**
 * Political / macro event categories added in the 2026-07-04 K12
 * expansion. These are the values the LLM prompt in
 * ``app/services/news/sentiment/prompts.py`` now documents; the
 * backend filters by them on the ``event_category`` query parameter.
 *
 * The chip strip surfaces them in a single row so the user can pivot
 * from "all news" to "geopolitics + central_bank" without typing.
 */
const POLITICAL_CATEGORIES: { value: string; label: string; color: string }[] = [
  { value: 'geopolitics', label: '地缘', color: 'volcano' },
  { value: 'central_bank', label: '央行', color: 'geekblue' },
  { value: 'election', label: '选举', color: 'purple' },
  { value: 'trade_war', label: '贸易战', color: 'red' },
  { value: 'sanction', label: '制裁', color: 'magenta' },
];

/** Build ISO date for `dayjs()` value. */
function toIso(d: Dayjs | null | undefined, endOfDay = false): string | undefined {
  if (!d) return undefined;
  return (endOfDay ? d.endOf('day') : d.startOf('day')).toISOString();
}


/** Right column: per-symbol retail sentiment ranking. */
function HotSymbolSidebar({
  data,
  loading,
  onPickSymbol,
}: {
  data: {
    symbol: string;
    name?: string | null;
    name_zh?: string | null;
    label: SentimentLabel | null;
    score: number | null;
    count: number;
  }[];
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
        <LoadingBlock size="md" />
      ) : data.length === 0 ? (
        <EmptyState title="暂无情绪数据" description="当前没有可用的市场情绪聚合" />
      ) : (
        <div>
          {data.map((row) => {
            const tone = row.label
              ? SENTIMENT_COLORS[row.label]
              : 'var(--text-tertiary)';
            return (
              <div
                key={row.symbol}
                role="button"
                tabIndex={0}
                aria-label={`筛选 ${row.symbol} 的资讯`}
                onClick={() => onPickSymbol(row.symbol)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onPickSymbol(row.symbol);
                  }
                }}
                className="ad-mover-row"
              >
                <div className="ad-flex-1 ad-min-w-0">
                  <div className="ad-font-medium ad-text-primary ad-truncate">
                    <InstrumentCodeTag
                      code={row.symbol}
                      name={row.name ?? undefined}
                      name_zh={row.name_zh}
                    />
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
  const isMobile = useIsMobile();
  // Color convention drives the sentiment-legend colour words: A-share
  // (china) is 红涨绿跌 → positive=红 / negative=绿; US convention inverts it.
  const colorConvention = useSettingsStore((s) => s.colorConvention);
  // Article shown in the detail drawer (replaces the old ``/news/:id``
  // navigation; the route stays for deep links — see NewsDetailDrawer).
  const [selectedArticle, setSelectedArticle] = useState<NewsArticle | null>(null);
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
  // ``important=1`` turns on the "只看重要 ★4+" filter — wires the
  // backend ``importance_min`` query parameter (already supported by
  // ``GET /news``, see ``app/api/v1/news.py``) into the filter bar so
  // the LLM importance rating becomes a noise-reduction switch.
  // Only applies to the plain list feed: ``/news/watchlist`` has no
  // importance filter server-side, so the chip hides in watchlist mode.
  const [importantOnly, setImportantOnly] = useState<boolean>(
    searchParams.get('important') === '1'
  );
  // Selected political / macro event categories (multi-select).
  // Empty array = no filter (show all categories).
  const [eventCategories, setEventCategories] = useState<string[]>(() => {
    const raw = searchParams.get('event_category');
    if (raw) return raw.split(',').filter(Boolean);
    // M22-2 (2026-07-04): when the URL already pins the page to
    // ``market=global``, pre-light the political / macro chip strip
    // so the user lands on the most useful filter set.
    const initialMarket = searchParams.get('market');
    if (initialMarket === 'global') return [...GLOBAL_DEFAULT_CATEGORIES];
    return [];
  });

  /**
   * Wrap ``setMarket`` so switching to ``global`` automatically
   * lights the political-category chips (unless the user has already
   * pinned specific categories via the URL).
   */
  const handleSetMarket = (next: NewsMarket | 'all') => {
    setMarket(next);
    if (next === 'global' && eventCategories.length === 0) {
      setEventCategories([...GLOBAL_DEFAULT_CATEGORIES]);
    }
  };
  const debouncedSearchInput = useDebounce(searchInput, 300);

  // Sync URL params when filters change.
  // NB: drive the URL ``q`` from the debounced value so we are not
  // rewriting history on every keystroke (Response principle — kill
  // latency). The actual list query is also keyed off the debounced
  // value, so the URL stays in lockstep with the rendered result set.
  useEffect(() => {
    const next: Record<string, string> = {};
    if (market !== 'all') next.market = market;
    if (source) next.source = source;
    if (activeSymbol) next.symbol = activeSymbol;
    if (debouncedSearchInput) next.q = debouncedSearchInput;
    if (watchlistMode) next.watchlist = '1';
    if (importantOnly && !watchlistMode) next.important = '1';
    if (eventCategories.length > 0) next.event_category = eventCategories.join(',');
    setSearchParams(next, { replace: true });
  }, [market, source, activeSymbol, debouncedSearchInput, watchlistMode, importantOnly, eventCategories, setSearchParams]);

  // Source list for the dropdown.
  const { data: sourceStats, isLoading: sourceStatsLoading } = useQuery({
    queryKey: ['news-source-stats'],
    queryFn: () => newsApi.sourceStats().then((r) => r.data),
    staleTime: 5 * 60_000,
  });

  const sourceOptions = useMemo(() => {
    const stats = sourceStats?.sources ?? [];
    return stats.map((s) => ({
      value: s.source,
      label: `${SOURCE_LABELS[s.source]?.label ?? s.source} (${s.total})`,
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
    refetch,
  } = useInfiniteQuery({
    // Distinct query keys so the watchlist and global feeds do not
    // share a cache entry — the watchlist result set changes the
    // moment the user adds/removes a favorite.
    queryKey: watchlistMode
      ? ['news-watchlist', market, source, dateRange, eventCategories]
      : ['news-list', market, source, dateRange, activeSymbol, debouncedSearchInput, importantOnly, eventCategories],
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      watchlistMode
        ? newsApi
            .watchlist({
              market: market === 'all' ? undefined : market,
              source,
              from_date: toIso(dateRange?.[0] ?? null, false),
              to_date: toIso(dateRange?.[1] ?? null, true),
              event_category: eventCategories.length > 0 ? eventCategories : undefined,
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
              q: debouncedSearchInput || undefined,
              importance_min: importantOnly ? 4 : undefined,
              event_category: eventCategories.length > 0 ? eventCategories : undefined,
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
  // NOTE: avoid callback refs that return a cleanup function — React 18
  // warns about it and React 19 treats it as a cleanup, but our current
  // bundle is pinned to React 18 where the behaviour is inconsistent.
  const sentinelNodeRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const node = sentinelNodeRef.current;
    if (!node || !hasNextPage || isFetchingNextPage) return;
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
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const articles = useMemo(() => {
    return (data?.pages ?? [])
      .flatMap((p) => p?.items ?? [])
      .filter((a): a is NewsArticle => a != null && typeof a === 'object');
  }, [data]);

  // Aggregate top-10 symbols by importance-weighted sentiment for sidebar.
  const hotSymbols = useMemo(() => {
    const bucket = new Map<
      string,
      {
        count: number;
        weighted: number;
        scoreSum: number;
        positive: number;
        negative: number;
        neutral: number;
        name: string | null;
        name_zh: string | null;
      }
    >();
    for (const a of articles) {
      const symbols = a.symbols ?? [];
      for (const s of symbols) {
        if (!s) continue;
        const cur = bucket.get(s.symbol) ?? {
          count: 0,
          weighted: 0,
          scoreSum: 0,
          positive: 0,
          negative: 0,
          neutral: 0,
          name: s.name ?? null,
          name_zh: s.name_zh ?? null,
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
        return { symbol, name: v.name, name_zh: v.name_zh, count: v.count, score, label };
      })
      .filter((r) => r.count > 0)
      .sort((a, b) => b.count - a.count)
      .slice(0, 10);
  }, [articles]);

  const handleOpen = (a: NewsArticle) => {
    setSelectedArticle(a);
  };

  const handlePickSymbol = (sym: string) => {
    setActiveSymbol(sym);
    message.info(`已筛选标的: ${sym}`);
  };

  const totalLabel = watchlistMode && watchlistMeta
    ? `自选标的 ${watchlistMeta.symbols.length} 个 · 相关资讯 ${watchlistMeta.total_articles} 条`
    : `共 ${data?.pages?.[0]?.total ?? 0} 条`;

  // Active filter count for the mobile 筛选 badge (P3).
  const activeFilterCount =
    (market !== 'all' ? 1 : 0) +
    (source ? 1 : 0) +
    (activeSymbol ? 1 : 0) +
    (debouncedSearchInput ? 1 : 0) +
    (watchlistMode ? 1 : 0) +
    (importantOnly && !watchlistMode ? 1 : 0) +
    (dateRange?.[0] || dateRange?.[1] ? 1 : 0) +
    eventCategories.length;

  const handleResetFilters = () => {
    setMarket('all');
    setSource(undefined);
    setSearchInput('');
    setActiveSymbol(undefined);
    setWatchlistMode(false);
    setImportantOnly(false);
    setEventCategories([]);
    setDateRange(null);
  };

  // Shared filter controls — inside FilterToolbar on desktop, inside
  // the BottomSheet on mobile. Kept as JSX elements (not closure
  // components) so input focus survives re-renders.
  const filterControls = (
    <>
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
              // The watchlist endpoint has no importance filter —
              // drop the chip so it does not silently stop applying.
              setImportantOnly(false);
            }
          }}
          className={`ad-status-chip ${watchlistMode ? 'ad-status-chip--active' : ''}`}
        >
          <StarFilled className="ad-mr-1 ad-text-xs" />
          我的自选
        </Tag.CheckableTag>
        {!watchlistMode && (
          /* "只看重要 ★4+" — the LLM already rates every article 1-5;
             this wires the backend ``importance_min=4`` parameter into
             a one-tap noise filter. Hidden in watchlist mode because
             ``/news/watchlist`` has no importance filter server-side. */
          <Tag.CheckableTag
            checked={importantOnly}
            onChange={(checked) => setImportantOnly(checked)}
            className={`ad-status-chip ${importantOnly ? 'ad-status-chip--active' : ''}`}
          >
            <StarFilled className="ad-mr-1 ad-text-xs" />
            只看重要 ★4+
          </Tag.CheckableTag>
        )}
        <Segmented
          value={market}
          onChange={(v) => handleSetMarket(v as NewsMarket | 'all')}
          options={MARKET_OPTIONS}
          className="news-market-segmented"
        />
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="搜索标题/正文…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
        <Select
          allowClear
          placeholder="来源"
          loading={sourceStatsLoading}
          value={source}
          onChange={(v) => setSource(v)}
          options={sourceOptions}
          // 2026-08-03：来源标签形如「华尔街日报 (1,234)」，原先 Select
          // 无宽度约束收缩到占位符宽度，下拉项全部截断成「新…/yah…」。
          // minWidth 撑开输入框 + popupMatchSelectWidth=false 让下拉面板
          // 按内容自适应；800+ 源加 showSearch 直接输入过滤。
          style={{ minWidth: 220 }}
          popupMatchSelectWidth={false}
          showSearch
          optionFilterProp="label"
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
    </>
  );

  const politicalChips = (
    <>
      {/* Political / macro event category chips (K12 addition).
          Multi-select: clicking toggles a category in/out of the
          filter set. The active set is persisted into the URL so
          the view is shareable. */}
      <div className="news-political-chips ad-flex ad-flex-wrap ad-gap-2 ad-mb-3">
        <span className="ad-text-small ad-text-tertiary ad-self-center ad-mr-1 news-political-chips__label">
          事件类型:
        </span>
        {POLITICAL_CATEGORIES.map((c) => {
          const checked = eventCategories.includes(c.value);
          return (
            <Tag.CheckableTag
              key={c.value}
              checked={checked}
              onChange={(next) => {
                setEventCategories((prev) =>
                  next
                    ? Array.from(new Set([...prev, c.value]))
                    : prev.filter((v) => v !== c.value),
                );
              }}
              className={`news-political-chip news-political-chip--${c.value} ${checked ? 'news-political-chip--active' : ''}`}
            >
              {c.label}
            </Tag.CheckableTag>
          );
        })}
        {eventCategories.length > 0 && (
          <Tag.CheckableTag
            checked={false}
            onChange={() => setEventCategories([])}
            className="news-political-chip news-political-chip--clear"
          >
            清除
          </Tag.CheckableTag>
        )}
      </div>
    </>
  );

  return (
    <PageShell maxWidth="wide">
      <style>{NEWS_PAGE_STYLE}</style>
      <PageHeader
        title="资讯"
        description="多市场新闻聚合 · 情绪与重要性实时标注"
      />

      {isMobile ? (
        /* P3 (方向 C): mobile first screen carries zero filter chrome —
           the full filter form (market / source / date / event chips)
           lives in the half sheet behind 筛选. */
        <div className="mobile-filter-bar">
          <FilterSheetButton
            activeCount={activeFilterCount}
            onReset={handleResetFilters}
          >
            {filterControls}
            {politicalChips}
          </FilterSheetButton>
          <span className="mobile-filter-bar__meta">{totalLabel}</span>
        </div>
      ) : (
        <>
          <FilterToolbar total={totalLabel} className="news-feed-toolbar">
            {filterControls}
          </FilterToolbar>
          {politicalChips}
        </>
      )}

      <div className="ad-news-layout">
        {/* Feed */}
        <div className="ad-news-feed">
          {isError ? (
            /* N1（2026-08-03）：加载失败给出明确的重试出口，
               不再只能整页刷新。 */
            <EmptyState
              title="加载失败，请稍后重试"
              description="网络异常或服务暂不可用，请稍后再试"
              action={
                <Button type="primary" onClick={() => refetch()}>
                  重试
                </Button>
              }
            />
          ) : isLoading ? (
            <div className="ad-p-5">
              <LoadingBlock size="lg" />
            </div>
          ) : articles.length === 0 ? (
            <EmptyState
              title="暂无符合筛选条件的资讯"
              description="尝试调整上方筛选条件、清空关键词或切换市场"
            />
          ) : (
            <>
              {articles.map((a) => (
                <NewsCard
                  key={a.id}
                  article={a}
                  onOpen={handleOpen}
                  onPickSymbol={handlePickSymbol}
                />
              ))}
              <div
                ref={sentinelNodeRef}
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
              {(['positive', 'neutral', 'negative'] as SentimentLabel[]).map((l) => {
                const colorWord =
                  l === 'neutral'
                    ? '灰'
                    : l === 'positive'
                    ? colorConvention === 'china'
                      ? '红'
                      : '绿'
                    : colorConvention === 'china'
                    ? '绿'
                    : '红';
                return (
                  <div key={l} className="ad-flex ad-items-center ad-gap-2">
                    <Badge color={SENTIMENT_COLORS[l]} />
                    <span className="ad-text-small ad-text-secondary">
                      {SENTIMENT_LABELS[l]} ({colorWord})
                    </span>
                  </div>
                );
              })}
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

      <NewsDetailDrawer
        article={selectedArticle}
        onClose={() => setSelectedArticle(null)}
        onPickSymbol={handlePickSymbol}
      />
    </PageShell>
  );
}
