import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, List, Skeleton, Tooltip } from 'antd';
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
  FolderOpenOutlined,
  FireOutlined,
  StarFilled,
  ReadOutlined,
  GlobalOutlined,
  BookOutlined,
  LineChartOutlined,
  ExperimentOutlined,
  WalletOutlined,
  DollarOutlined,
  AppstoreOutlined,
  ThunderboltOutlined,
  PartitionOutlined,
} from '@ant-design/icons';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { useScores } from '@/hooks/useScores';
import { useFavorites } from '@/hooks/useFavorites';
import { usePoolList } from '@/hooks/usePoolDetail';
import { statsApi } from '@/api/stats';
import {
  formatDateTime,
  formatDateTimeCompact,
  formatRelative as formatRelativeTz,
} from '@/utils/datetime';
import { newsApi } from '@/api/news';
import { useMacroLatest } from '@/api/macro';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import SectionHeading from '@/components/SectionHeading';
import StatCard from '@/components/StatCard';
import EmptyState from '@/components/EmptyState';
import LoadingBlock from '@/components/LoadingBlock';
import Panel from '@/components/Panel';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import ReturnTag from '@/components/ReturnTag';
import ThemeTag from '@/components/ThemeTag';
import ScoreBar from '@/components/ScoreBar';
import FavoriteToggleButton from '@/components/FavoriteToggleButton';
import TickerTape from '@/components/TickerTape';
import HelpPopover from '@/components/HelpPopover';
import DailyLesson from '@/components/DailyLesson';
import DataFreshnessHint from '@/components/DataFreshnessHint';
import { useLearnStats } from '@/hooks/useLearnedTerms';
import { useSettingsStore } from '@/stores/settings';
import { usePriceStream } from '@/hooks/usePriceStream';
import { useMarketStream } from '@/hooks/useMarketStream';
import type { NewsArticle } from '@/types/news';
import { SENTIMENT_COLORS, SENTIMENT_LABELS } from '@/utils/sentiment';



function formatRelative(iso: string): string {
  // UTC-aware formatter — see ``utils/datetime``.
  return formatRelativeTz(iso, { withTimeAfterDays: 7 });
}

/** Compact news row used in dashboard cards. */
function NewsRow({
  article,
  onOpen,
}: {
  article: NewsArticle;
  onOpen: (id: number) => void;
}) {
  const filled = article.importance ? Math.max(0, Math.min(5, article.importance)) : 0;
  return (
    <div
      className="dashboard-news-row"
      onClick={() => onOpen(article.id)}
    >
      <div className="dashboard-news-row__meta">
        <span>{article.source}</span>
        <span className="dashboard-news-row__divider">·</span>
        <Tooltip title={formatDateTime(article.published_at)}>
          <span>{formatRelative(article.published_at)}</span>
        </Tooltip>
        {article.importance ? (
          <span className="dashboard-news-row__importance">
            {Array.from({ length: 5 }).map((_, i) => (
              <StarFilled
                key={i}
                className={`dashboard-news-row__star ${
                  i < filled ? 'dashboard-news-row__star--filled' : 'dashboard-news-row__star--empty'
                }`}
              />
            ))}
          </span>
        ) : null}
      </div>
      <div className="dashboard-news-row__title">{article.title}</div>
      <div className="dashboard-news-row__tags">
        {article.symbols.slice(0, 4).map((s) => (
          <ThemeTag key={`${s.symbol}-${s.match_type}`} className="dashboard-news-row__tag">
            <InstrumentCodeTag code={s.symbol} name={s.name ?? undefined} name_zh={s.name_zh} />
          </ThemeTag>
        ))}
        <span className="dashboard-news-row__spacer" />
        {article.sentiment_label && (
          <Tooltip title={SENTIMENT_LABELS[article.sentiment_label]}>
            <span
              aria-label={SENTIMENT_LABELS[article.sentiment_label]}
              className="dashboard-news-row__sentiment ad-rise-fall-sentiment"
              style={{ color: SENTIMENT_COLORS[article.sentiment_label] }}
            >
              {SENTIMENT_LABELS[article.sentiment_label]}
            </span>
          </Tooltip>
        )}
      </div>
    </div>
  );
}

/**
 * Top-of-dashboard "全球速览" — pulls headline overseas indicators
 * from the Macro API (FRED + yfinance + akshare).
 *
 * Coverage (Phase 2, 2026-07-07): FRED for US rates / VIX / DXY /
 * Brent / WTI / SP500; yfinance for Hang Seng, Nikkei, DAX, FTSE,
 * CAC, ASX, KOSPI, NIFTY; akshare for SHCOMP / SZC. All codes are
 * resolved via ``useMacroLatest('us' | 'global')`` so the same
 * ingestion rows power the Global Markets page.
 *
 * The ResponsiveGrid is 8-tile wide on lg / 4 on md — the row is split
 * across two lines so it stays readable on tablet portrait. Tiles
 * gracefully render `--` when a particular code has no fresh data
 * (e.g. yfinance fetch failed overnight).
 */
const GLOBAL_TILES: Array<{
  code: string;
  title: string;
  unit: string;
}> = [
  // ── 美股大盘 ──
  { code: 'global_sp500', title: '标普 500', unit: '' },
  { code: 'global_ndx', title: '纳斯达克 100', unit: '' },
  { code: 'global_dow', title: '道琼斯', unit: '' },
  // ── 美债 / 汇率 ──
  { code: 'us_dgs10', title: 'US 10Y', unit: '%' },
  { code: 'usd_cny', title: 'USD/CNY', unit: '' },
  { code: 'usd_eur', title: 'USD/EUR', unit: '' },
  { code: 'us_t10y3m', title: 'US T10Y3M', unit: '%' },
  // ── 亚太 ──
  { code: 'global_shcomp', title: '上证综指', unit: '' },
  { code: 'global_hsi', title: '恒生指数', unit: '' },
  { code: 'global_n225', title: '日经 225', unit: '' },
  { code: 'global_szse', title: '深证成指', unit: '' },
  { code: 'global_kospi', title: 'KOSPI', unit: '' },
  // ── 欧洲 ──
  { code: 'global_ftse', title: '富时 100', unit: '' },
  { code: 'global_dax', title: 'DAX', unit: '' },
  { code: 'global_cac', title: 'CAC 40', unit: '' },
];

function formatTileValue(v: number | null | undefined, unit: string): string {
  if (v == null || Number.isNaN(v)) return '—';
  if (unit === '%') return `${v.toFixed(2)}%`;
  if (Math.abs(v) >= 1000)
    return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return v.toFixed(2);
}

function GlobalSnapshot() {
  const navigate = useNavigate();
  const { data: latestGlobal, isLoading: gLoading } = useMacroLatest('global');
  const { data: latestUs, isLoading: uLoading } = useMacroLatest('us');

  const lookup = useMemo(() => {
    const map = new Map<string, { value: number | null; period: string | null; change_pct: number | null }>();
    for (const it of latestGlobal?.items ?? []) {
      map.set(it.code, { value: it.value ?? null, period: it.period ?? null, change_pct: it.change_pct ?? null });
    }
    for (const it of latestUs?.items ?? []) {
      if (!map.has(it.code)) {
        map.set(it.code, { value: it.value ?? null, period: it.period ?? null, change_pct: it.change_pct ?? null });
      }
    }
    return map;
  }, [latestGlobal, latestUs]);

  const isLoading = gLoading || uLoading;
  const hasAnyData = GLOBAL_TILES.some((t) => lookup.has(t.code));

  return (
    <section className="dashboard-section">
      <SectionHeading
        eyebrow="海外宏观"
        title={
          <span>
            <GlobalOutlined className="ad-icon-accent" /> 全球速览
          </span>
        }
        action={
          <span
            className="panel-extra-link"
            onClick={() => navigate('/global')}
          >
            查看全部 →
          </span>
        }
      />
      {!hasAnyData && !isLoading ? (
        <Panel>
          <EmptyState
            title="暂无全球宏观数据"
            description="FRED 尚未采集或未配置 API Key。前往「全球市场」页面查看详情。"
          />
        </Panel>
      ) : (
        <ResponsiveGrid cols={4} gap="md">
          {GLOBAL_TILES.map((tile) => {
            const entry = lookup.get(tile.code);
            return (
              <Panel
                key={tile.code}
                variant="default"
                padding="md"
                className="dashboard-index-card"
              >
                <div
                  className="dashboard-index-card__cover"
                  role="button"
                  tabIndex={0}
                  onClick={() => navigate('/global')}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      navigate('/global');
                    }
                  }}
                  aria-label={`查看 ${tile.title}`}
                />
                <div className="dashboard-index-card__header">
                  <span className="dashboard-index-card__code">{tile.code}</span>
                </div>
                <div className="dashboard-index-card__price">
                  {isLoading && !entry ? (
                    <span className="dashboard-index-card__empty">加载中...</span>
                  ) : (
                    formatTileValue(entry?.value ?? null, tile.unit)
                  )}
                </div>
                <div className="dashboard-index-card__footer">
                  <span className="dashboard-index-card__empty">
                    {tile.title}
                  </span>
                  {entry?.change_pct != null ? (
                    <ReturnTag value={entry.change_pct} />
                  ) : (
                    <span className="dashboard-index-card__empty">—</span>
                  )}
                  {entry?.period ? (
                    <span className="dashboard-index-card__timestamp">
                      {entry.period}
                    </span>
                  ) : null}
                </div>
              </Panel>
            );
          })}
        </ResponsiveGrid>
      )}
    </section>
  );
}

/**
 * Hook: bundle the 4 dashboard KPI counters into per-metric queries.
 *
 * Each call hits ``/stats/overview/{metric}`` (a single COUNT / MAX
 * aggregate scoped to that field) so the 4 cards render in parallel and
 * don't block on each other. ``placeholderData: keepPreviousData``
 * keeps stale values visible across route changes, and ``isPending``
 * (i.e. no value yet, no cached placeholder) drives ``isLoading`` so
 * the StatCard skeleton still appears on a cold first paint.
 *
 * Returns one cell per metric plus the most-recent dataUpdatedAt (used
 * by the DataFreshnessHint). When the user navigates away and back,
 * ``updatedAt`` reflects whichever query most recently refetched —
 * close enough for "data is fresh as of N seconds ago".
 */
function useDashboardStatsKpis() {
  const sharedOptions = {
    staleTime: 30_000,
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  } as const;

  const etf = useQuery({
    queryKey: ['stats-overview', 'etf-count'],
    queryFn: () => statsApi.metric('etf-count'),
    ...sharedOptions,
  });
  const score = useQuery({
    queryKey: ['stats-overview', 'score-count'],
    queryFn: () => statsApi.metric('score-count'),
    ...sharedOptions,
  });
  const category = useQuery({
    queryKey: ['stats-overview', 'category-count'],
    queryFn: () => statsApi.metric('category-count'),
    ...sharedOptions,
  });
  const template = useQuery({
    queryKey: ['stats-overview', 'template-count'],
    queryFn: () => statsApi.metric('template-count'),
    ...sharedOptions,
  });

  const cell = (q: { data: number | undefined; isPending: boolean }) => ({
    value: q.data ?? 0,
    isLoading: q.isPending && q.data == null,
  });

  return {
    'etf-count': cell(etf),
    'score-count': cell(score),
    'category-count': cell(category),
    'template-count': cell(template),
    etf: etf.data ?? 0,
    score: score.data ?? 0,
    category: category.data ?? 0,
    template: template.data ?? 0,
    updatedAt:
      Math.max(
        etf.dataUpdatedAt ?? 0,
        score.dataUpdatedAt ?? 0,
        category.dataUpdatedAt ?? 0,
        template.dataUpdatedAt ?? 0,
      ) || undefined,
  };
}

export default function Dashboard() {
  const navigate = useNavigate();
  const mode = useSettingsStore((s) => s.mode);
  const learnStats = useLearnStats();
  const { data: scoresData } = useScores({ limit: 10 });
  const { favorites, count: favCount, isLoading: favLoading } = useFavorites(10);
  const { data: pools, isLoading: poolsLoading } = usePoolList();
  // Dashboard 4 KPI tiles — each card fires its own per-metric query so
  // the four numbers render in parallel as soon as each one lands, instead
  // of waiting for a single bundled round-trip to finish. Each query
  // keeps its previous value via ``placeholderData: keepPreviousData``
  // so navigating away and back never shows a blank skeleton when the
  // cache is warm. Cold first paint shows 4 individual skeletons for
  // ~100-300 ms before numbers stream in.
  //   - staleTime: 30s — counts are slow-movers but for a daily-use
  //     dashboard we want to pick up an overnight ingest within ~30s
  //     without hammering the API on every focus change.
  //   - refetchOnWindowFocus: false — KPI counts don't change that fast;
  //     keeps the focus handler cheap.
  const statsKpis = useDashboardStatsKpis();

  // Hot news: importance >= 4, latest 6.
  const { data: hotNews, isLoading: hotNewsLoading } = useQuery({
    queryKey: ['dashboard-hot-news'],
    queryFn: () =>
      newsApi
        .list({ importance_min: 4, page: 1, page_size: 6 })
        .then((r) => r.data.items),
    staleTime: 60_000,
  });

  // Favorites news: pull each favorite's news, dedup, sort by recency.
  const { data: favoritesNews, isLoading: favNewsLoading } = useQuery({
    queryKey: ['dashboard-favorites-news', favorites?.map((f: any) => f.etf_code).join(',')],
    queryFn: async () => {
      if (!favorites || favorites.length === 0) return [] as NewsArticle[];
      const codes = favorites.slice(0, 5).map((f: any) => f.etf_code);
      const results = await Promise.all(
        codes.map((code: string) =>
          newsApi
            .list({ symbol: code, page: 1, page_size: 4 })
            .then((r) => r.data.items)
            .catch(() => [] as NewsArticle[])
        )
      );
      const merged = results
        .flat()
        .sort(
          (a, b) =>
            new Date(b.published_at).getTime() - new Date(a.published_at).getTime()
        );
      // Dedup by id.
      const seen = new Set<number>();
      const dedup: NewsArticle[] = [];
      for (const n of merged) {
        if (seen.has(n.id)) continue;
        seen.add(n.id);
        dedup.push(n);
      }
      return dedup.slice(0, 6);
    },
    enabled: favCount > 0,
    staleTime: 60_000,
  });

  const INDEX_CODES = ['510300.SH', '159915.SZ', 'SPY.US', 'BTC.US'];
  const { prices } = usePriceStream(INDEX_CODES);
  // MarketStream supersedes the price stream for the live tickers: it
  // surfaces timestamps and the upstream connection state, so the four
  // dashboard cards can show "updated 3s ago" hints.
  const { latest: marketLatest, isConnected: marketConnected, reconnect: marketReconnect } =
    useMarketStream(INDEX_CODES);

  const scoreColumns = [
    {
      title: <HelpPopover termKey="rank_overall" mode={mode}>排名</HelpPopover>,
      dataIndex: 'rank_overall',
      width: 70,
      render: (v: number) => (
        <span
          className={`tabular-nums dashboard-rank-cell ${v <= 3 ? 'dashboard-rank-cell--top3' : 'dashboard-rank-cell--normal'}`}
        >
          {v}
        </span>
      ),
    },
    {
      title: '标的',
      render: (_: unknown, record: any) => (
        <InstrumentCodeTag code={record.etf_code} name={record.etf_name} />
      ),
    },
    {
      title: <HelpPopover termKey="composite_score" mode={mode}>评分</HelpPopover>,
      render: (_: unknown, record: any) => (
        <ScoreBar score={record.composite_score} size="small" />
      ),
      width: 160,
    },
    {
      title: <HelpPopover termKey="return_1m" mode={mode}>1月收益</HelpPopover>,
      render: (_: unknown, record: any) => <ReturnTag value={record.return_1m} />,
      width: 110,
    },
    {
      title: '趋势',
      width: 60,
      render: (_: unknown, record: any) =>
        record.return_1m >= 0 ? (
          <ArrowUpOutlined className="ad-icon-rise" />
        ) : (
          <ArrowDownOutlined className="ad-icon-fall" />
        ),
    },
    {
      title: '',
      key: 'favorite',
      width: 48,
      render: (_: unknown, record: any) => (
        <FavoriteToggleButton code={record.etf_code} name={record.etf_name} />
      ),
    },
  ];

  return (
    <PageShell maxWidth="full" className="dashboard-shell">
      <TickerTape limit={20} />

      <PageHeader
        eyebrow={`AD-RESEARCH · ${new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })} · A股全市场综述`}
        title="首页看板"
        description={
          <span>
            综合评分 · 收藏 · 标的池概览 · {new Date().toISOString().slice(0, 10)}
            {' · '}
            <DataFreshnessHint at={statsKpis.updatedAt} />
          </span>
        }
        extra={
          <span className="dashboard-shell__quickbar">
            <ThemeTag variant="accent" icon={<BookOutlined />} onClick={() => navigate('/learning')}>教程总览</ThemeTag>
            <ThemeTag variant="accent" icon={<LineChartOutlined />} onClick={() => navigate('/learning')}>看估值</ThemeTag>
            <ThemeTag variant="neutral" icon={<ExperimentOutlined />} onClick={() => navigate('/learning')}>做回测</ThemeTag>
            <ThemeTag variant="warning" icon={<WalletOutlined />} onClick={() => navigate('/portfolio')}>组合中心</ThemeTag>
            <ThemeTag variant="neutral" icon={<DollarOutlined />} onClick={() => navigate('/paper-trading')}>模拟账户</ThemeTag>
            <ThemeTag variant="neutral" icon={<ThunderboltOutlined />} onClick={() => navigate('/live-trading')}>真实账户</ThemeTag>
            <ThemeTag variant="default" icon={<AppstoreOutlined />} onClick={() => navigate('/pools')}>标的池</ThemeTag>
            <ThemeTag variant="warning" icon={<PartitionOutlined />} onClick={() => navigate('/learning?panel=terms')}>知识图谱</ThemeTag>
            {learnStats.total > 0 && (
              <span className="dashboard-shell__learn-meta">
                本周已学 {learnStats.total} 个术语
              </span>
            )}
          </span>
        }
      />

      {/* KPI strip — 4 StatCards. Each card binds to its own per-metric
         query so numbers stream in independently (Phase 2, 2026-07-07). */}
      <section className="dashboard-section">
        <SectionHeading title="核心指标" />
        <ResponsiveGrid cols={4} gap="md">
          {[
            {
              title: '标的总数',
              metric: 'etf-count' as const,
              suffix: undefined,
              onClick: () => navigate('/instruments'),
              term: 'etf',
            },
            {
              title: '评分覆盖',
              metric: 'score-count' as const,
              suffix: statsKpis.etf > 0 ? `/ ${statsKpis.etf}` : undefined,
              onClick: () => navigate('/scores'),
              term: 'composite_score',
            },
            {
              title: '分类数',
              metric: 'category-count' as const,
              suffix: undefined,
              onClick: undefined,
              term: 'rank_category',
            },
            {
              title: '评分模板',
              metric: 'template-count' as const,
              suffix: undefined,
              onClick: () => navigate('/scores'),
              term: 'strategy_template',
            },
          ].map((item) => {
            const cell = statsKpis[item.metric];
            return (
              <StatCard
                key={item.title}
                title={item.title}
                value={cell.value}
                suffix={item.suffix}
                loading={cell.isLoading}
                onClick={item.onClick}
                term={item.term}
              />
            );
          })}
        </ResponsiveGrid>
      </section>

      {/* Daily lesson — full width row, kept simple */}
      {/* Daily lesson — full width row.
         Phase 2 (2026-07-05): DailyLesson carries its own card surface
         (lighter glass + --radius-lg) so we no longer nest it inside a
         Panel — eliminates the previous double-box visual. */}
      <section className="dashboard-section">
        <SectionHeading title="今日一课" />
        <DailyLesson />
      </section>

      {/* ── Global markets snapshot (P0: 2026-07-04) ─────────────────── */}
      <GlobalSnapshot />

      <section className="dashboard-section">
        <SectionHeading
          title="实时行情"
          action={
            !marketConnected ? (
              <span className="market-conn">
                <span className="market-conn__pill">连接中断</span>
                <button
                  type="button"
                  className="market-conn__retry"
                  onClick={marketReconnect}
                >
                  重新连接
                </button>
              </span>
            ) : undefined
          }
        />
        <ResponsiveGrid cols={4} gap="md">
          {INDEX_CODES.map((code, i) => {
            const tick = marketLatest[code] ?? (prices[code]
              ? { ...prices[code], ts: 0, name: undefined, market: undefined }
              : undefined);
            return (
              <Panel key={code} variant="default" padding="md" className="dashboard-index-card">
                <div className="dashboard-index-card__header">
                  <span className="dashboard-index-card__code">{code}</span>
                  {i === 0 ? (
                    <Tooltip
                      title={marketConnected ? 'SSE 已连接，3 秒刷新' : 'SSE 未连接，正在重连'}
                    >
                      <span
                        aria-label={marketConnected ? '实时连接中' : '连接断开'}
                        className={`dashboard-index-card__dot ${marketConnected ? 'dashboard-index-card__dot--connected' : ''}`}
                      />
                    </Tooltip>
                  ) : null}
                </div>
                <div className="dashboard-index-card__price">
                  {tick ? tick.price.toFixed(2) : '-'}
                </div>
                <div className="dashboard-index-card__footer">
                  {tick ? (
                    <>
                      <ReturnTag value={tick.change_pct} />
                      {tick.ts ? (
                        <Tooltip title={formatDateTime(tick.ts, 'YYYY-MM-DD HH:mm:ss')}>
                          <span className="dashboard-index-card__timestamp">
                            {formatDateTimeCompact(tick.ts)}
                          </span>
                        </Tooltip>
                      ) : null}
                    </>
                  ) : (
                    <span className="dashboard-index-card__empty">暂无数据</span>
                  )}
                </div>
              </Panel>
            );
          })}
        </ResponsiveGrid>
      </section>

      {/* News row: hot news + favorites news — responsive 2 col, stacks < 1024px */}
      <section className="dashboard-section dashboard-news-section">
        <ResponsiveGrid cols={2} gap="lg">
          <Panel
            variant="default"
            title={
              <span>
                <FireOutlined className="ad-icon-accent" />
                今日热点
              </span>
            }
            extra={
              <span className="panel-extra-link" onClick={() => navigate('/news')}>
                查看全部 →
              </span>
            }
          >
            {hotNewsLoading ? (
              <Skeleton active paragraph={{ rows: 5 }} />
            ) : !hotNews || hotNews.length === 0 ? (
              <EmptyState title="暂无重要资讯" />
            ) : (
              hotNews.map((a) => (
                <NewsRow key={a.id} article={a} onOpen={(id) => navigate(`/news/${id}`)} />
              ))
            )}
          </Panel>

          <Panel
            variant="default"
            title={
              <span>
                <ReadOutlined className="ad-icon-leading" />
                自选股动态
              </span>
            }
            extra={
              favCount > 0 ? (
                <span className="panel-extra-link" onClick={() => navigate('/news')}>
                  查看全部 →
                </span>
              ) : undefined
            }
          >
            {favNewsLoading ? (
              <Skeleton active paragraph={{ rows: 5 }} />
            ) : favCount === 0 ? (
              <EmptyState
                title="暂无收藏的标的"
                description="收藏自选股后，这里会汇总相关新闻"
              />
            ) : !favoritesNews || favoritesNews.length === 0 ? (
              <EmptyState title="暂无自选股相关资讯" />
            ) : (
              favoritesNews.map((a) => (
                <NewsRow key={a.id} article={a} onOpen={(id) => navigate(`/news/${id}`)} />
              ))
            )}
          </Panel>
        </ResponsiveGrid>
      </section>

      {/* Scores + side stack */}
      <section className="dashboard-section dashboard-score-grid">
        <ResponsiveGrid cols={2} gap="lg">
          <Panel
            variant="default"
            title="综合评分 Top 10"
            extra={
              <span className="panel-extra-link" onClick={() => navigate('/scores')}>
                查看全部 →
              </span>
            }
          >
            <Table
              dataSource={scoresData?.items || []}
              columns={scoreColumns}
              rowKey="etf_code"
              size="small"
              scroll={{ x: 'max-content' }}
              pagination={false}
              showHeader={false}
              onRow={(record) => ({ onClick: () => navigate(`/instruments/${record.etf_code}`) })}
            />
          </Panel>

          <div className="dashboard-side-stack">
            <Panel
              variant="default"
              title={
                <span>
                  <StarFilled className="ad-icon-accent" /> 我的收藏
                </span>
              }
              extra={
                favCount > 0 ? (
                  <span className="panel-extra-link" onClick={() => navigate('/favorites')}>
                    查看全部 →
                  </span>
                ) : (
                  <span className="panel-extra-link" onClick={() => navigate('/favorites')}>
                    前往自选 →
                  </span>
                )
              }
            >
              {favLoading ? (
                <LoadingBlock size="md" label="加载中…" />
              ) : favCount === 0 ? (
                <EmptyState
                  title="暂无收藏的标的"
                  description="在详情页点击 ★ 即可加入自选。这里会汇总你关注的标的、实时行情和相关新闻。"
                  action={
                    <span
                      className="panel-extra-link"
                      role="link"
                      tabIndex={0}
                      onClick={() => navigate('/favorites')}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          navigate('/favorites');
                        }
                      }}
                    >
                      前往「我的自选股」 →
                    </span>
                  }
                />
              ) : (
                <List
                  dataSource={favorites}
                  renderItem={(item: any) => (
                    <List.Item
                      onClick={() => navigate(`/instruments/${item.etf_code}`)}
                      className="dashboard-favorite-item"
                    >
                      <List.Item.Meta
                        title={
                          <div className="dashboard-favorite-item__title">
                            <InstrumentCodeTag code={item.etf_code} name={item.etf_name} />
                          </div>
                        }
                        description={
                          <div className="dashboard-favorite-item__desc">
                            <span>{item.category}</span>
                            <span className="ad-text-muted">|</span>
                            <span>{item.market}</span>
                          </div>
                        }
                      />
                    </List.Item>
                  )}
                />
              )}
            </Panel>

            <Panel
              variant="default"
              title="我的标的池"
              extra={
                (pools?.length || 0) > 0 ? (
                  <span className="panel-extra-link" onClick={() => navigate('/pools')}>
                    查看全部 →
                  </span>
                ) : undefined
              }
            >
              {poolsLoading ? (
                <LoadingBlock size="md" label="加载中…" />
              ) : (pools?.length || 0) === 0 ? (
                <EmptyState
                  title="暂无标的池"
                  description="在标的池管理中创建池并添加标的，这里会汇总展示"
                />
              ) : (
                <List
                  dataSource={pools?.slice(0, 6) || []}
                  renderItem={(pool: any) => (
                    <List.Item
                      onClick={() => navigate(`/pools/${pool.id}`)}
                      className="dashboard-pool-item"
                    >
                      <List.Item.Meta
                        title={
                          <div className="dashboard-pool-item__title">
                            <FolderOpenOutlined className="ad-icon-accent" />
                            <span className="dashboard-pool-item__name">{pool.name}</span>
                          </div>
                        }
                        description={
                          <div className="dashboard-pool-item__desc">
                            <span>{pool.members?.length || 0} 只标的</span>
                            {pool.description && (
                              <>
                                <span className="ad-text-muted">|</span>
                                <span>{pool.description}</span>
                              </>
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
        </ResponsiveGrid>
      </section>
    </PageShell>
  );
}
