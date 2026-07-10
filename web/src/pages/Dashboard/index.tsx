import './styles.css';

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
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { useScores } from '@/hooks/useScores';
import { useFavorites } from '@/hooks/useFavorites';
import { usePoolList } from '@/hooks/usePoolDetail';
import { statsApi } from '@/api/stats';
import {
  formatDateTime,
  formatRelative as formatRelativeTz,
} from '@/utils/datetime';
import { newsApi } from '@/api/news';
import { useMacroLatest, macroApi } from '@/api/macro';
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
import EtfHoldingsCoverageCard from '@/components/EtfHoldingsCoverageCard';
import { useSettingsStore } from '@/stores/settings';
import { usePriceStream } from '@/hooks/usePriceStream';
import { useMarketStream } from '@/hooks/useMarketStream';
import type { NewsArticle } from '@/types/news';
import { SENTIMENT_COLORS, SENTIMENT_LABELS } from '@/utils/sentiment';



function formatRelative(iso: string): string {
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
 * Global index tile definitions for the compact Pulse strip.
 * Each tile maps to a macro code resolved via useMacroLatest.
 */
const GLOBAL_TILES: Array<{
  code: string;
  title: string;
  unit: string;
}> = [
  // ── 美股大盘 ──
  { code: 'global_sp500', title: '标普 500', unit: '' },
  { code: 'global_nasdaq', title: '纳斯达克 100', unit: '' },
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

/* ================================================================
   PulseGlobalStrip — compact, borderless global index tiles.
   Replaces the old ResponsiveGrid + Panel GlobalSnapshot approach
   with an 8-column grid of transparent, minimal tiles.  Each tile
   shows the index name, value, and a change arrow; hover lifts 1px
   and the whole tile is a click target to /macro.
   ================================================================ */
function PulseGlobalStrip() {
  const navigate = useNavigate();
  const { data: latestGlobal, isLoading: gLoading } = useMacroLatest('global');
  const { data: latestUs, isLoading: uLoading } = useMacroLatest('us');
  const { data: rtGlobal, isLoading: rtLoading } = useQuery({
    queryKey: ['macro', 'indices', 'global', 'realtime'],
    queryFn: async () => {
      const res = await macroApi.getGlobalIndicesRealtime();
      return res.data;
    },
    staleTime: 60_000,
  });

  const lookup = useMemo(() => {
    type LookupEntry = {
      value: number | null;
      period: string | null;
      change_pct: number | null;
      source: string | null;
      freshness_hint: string | null;
    };
    const map = new Map<string, LookupEntry>();
    for (const it of latestGlobal?.items ?? []) {
      map.set(it.code, {
        value: it.value ?? null,
        period: it.period ?? null,
        change_pct: it.change_pct ?? null,
        source: it.source ?? null,
        freshness_hint: it.freshness_hint ?? null,
      });
    }
    for (const it of latestUs?.items ?? []) {
      if (!map.has(it.code)) {
        map.set(it.code, {
          value: it.value ?? null,
          period: it.period ?? null,
          change_pct: it.change_pct ?? null,
          source: it.source ?? null,
          freshness_hint: it.freshness_hint ?? null,
        });
      }
    }
    for (const it of rtGlobal?.items ?? []) {
      const code = it.code as string;
      const existing = map.get(code);
      const livePeriod = (it.as_of as string) ?? null;
      if (livePeriod != null && (existing == null || livePeriod > (existing.period ?? ''))) {
        map.set(code, {
          value: (it.value as number) ?? null,
          period: livePeriod,
          change_pct: (it.change_pct as number) ?? null,
          source: 'yfinance',
          freshness_hint: null,
        });
      }
    }
    return map;
  }, [latestGlobal, latestUs, rtGlobal]);

  const isLoading = gLoading || uLoading || rtLoading;

  return (
    <div className="dashboard-pulse-strip">
      {GLOBAL_TILES.map((tile) => {
        const entry = lookup.get(tile.code);
        const fresnessHint = entry?.freshness_hint ?? null;
        return (
          <div
            key={tile.code}
            className="dashboard-pulse-tile"
            role="button"
            tabIndex={0}
            onClick={() => navigate('/macro')}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                navigate('/macro');
              }
            }}
            aria-label={`${tile.title}: ${formatTileValue(entry?.value ?? null, tile.unit)}`}
          >
            {fresnessHint ? (
              <Tooltip title={fresnessHint}>
                <span className="dashboard-pulse-tile__freshness" aria-label={fresnessHint}>
                  <ExclamationCircleOutlined />
                </span>
              </Tooltip>
            ) : null}
            <span className="dashboard-pulse-tile__code">{tile.title}</span>
            <span className="dashboard-pulse-tile__value">
              {isLoading && !entry ? '—' : formatTileValue(entry?.value ?? null, tile.unit)}
            </span>
            {entry?.change_pct != null ? (
              <ReturnTag value={entry.change_pct} />
            ) : (
              <span className="dashboard-pulse-tile__flat">—</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Hook: bundle the 4 dashboard KPI counters into per-metric queries.
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
  const { data: scoresData } = useScores({ limit: 10 });
  const { favorites, count: favCount, isLoading: favLoading } = useFavorites(10);
  const { data: pools, isLoading: poolsLoading } = usePoolList();
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
  const { latest: marketLatest, isConnected: marketConnected, reconnect: marketReconnect } =
    useMarketStream(INDEX_CODES);

  const latestTickDate = useMemo(() => {
    const maxTs = INDEX_CODES.reduce<number>((max, code) => {
      const marketTs = marketLatest[code]?.ts;
      return marketTs && marketTs > max ? marketTs : max;
    }, 0);
    return maxTs > 0 ? new Date(maxTs).toISOString().slice(0, 10) : new Date().toISOString().slice(0, 10);
  }, [marketLatest]);

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
      {/* ── TickerTape: always the first thing the eye catches ── */}
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
          </span>
        }
      />

      {/* ═══════════════════════════════════════════════════════════
          ZONE 1: 市场脉搏 (PULSE)
          Compact, borderless, high information density.
          Answers: "Should I panic?"
          ═══════════════════════════════════════════════════════════ */}
      <section className="dashboard-section dashboard-zone dashboard-zone--pulse">
        <SectionHeading
          eyebrow="PULSE"
          title={
            <span>
              <GlobalOutlined className="ad-icon-accent" /> 市场脉搏
            </span>
          }
          action={
            <span
              className="panel-extra-link"
              onClick={() => navigate('/global')}
            >
              全球市场 →
            </span>
          }
        />

        {/* Global index strip: 8-col compact grid, transparent tiles */}
        <PulseGlobalStrip />

        {/* Real-time ticker cards: 4-col compact variant */}
        <div style={{ marginTop: 'var(--space-4)' }}>
          <div className="dashboard-pulse-strip dashboard-pulse-strip--4col" style={{ marginTop: 'var(--space-4)' }}>
            {INDEX_CODES.map((code, i) => {
              const tick = marketLatest[code] ?? (prices[code]
                ? { ...prices[code], ts: 0, name: undefined, market: undefined }
                : undefined);
              return (
                <div
                  key={code}
                  className="dashboard-pulse-tile"
                  role="button"
                  tabIndex={0}
                  onClick={() => navigate(`/instruments/${code}`)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      navigate(`/instruments/${code}`);
                    }
                  }}
                  aria-label={`${code}: ${tick ? tick.price.toFixed(2) : '暂无数据'}`}
                >
                  <span className="dashboard-pulse-tile__code">
                    {code}
                    {i === 0 && (
                      <Tooltip
                        title={marketConnected ? 'SSE 已连接，3 秒刷新' : 'SSE 未连接，正在重连'}
                      >
                        <span
                          aria-label={marketConnected ? '实时连接中' : '连接断开'}
                          style={{
                            display: 'inline-block',
                            width: 6,
                            height: 6,
                            borderRadius: '50%',
                            background: marketConnected ? 'var(--color-rise)' : 'var(--color-fall)',
                            marginLeft: 4,
                            verticalAlign: 'middle',
                          }}
                        />
                      </Tooltip>
                    )}
                  </span>
                  <span className="dashboard-pulse-tile__value">
                    {tick ? tick.price.toFixed(2) : '—'}
                  </span>
                  {tick ? (
                    <ReturnTag value={tick.change_pct} />
                  ) : (
                    <span className="dashboard-pulse-tile__flat">暂无数据</span>
                  )}
                </div>
              );
            })}
          </div>
          {!marketConnected && (
            <div style={{ marginTop: 8, textAlign: 'right' }}>
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
            </div>
          )}
          <div style={{ marginTop: 4, fontSize: 'var(--text-small-size)', color: 'var(--text-muted)', textAlign: 'right' }}>
            {latestTickDate}
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════
          ZONE 2: 我的关注 (MY WATCH)
          Standard card density — the user's personal dashboard.
          Answers: "How am I doing today?"
          ═══════════════════════════════════════════════════════════ */}
      <section className="dashboard-section dashboard-zone dashboard-zone--watch">
        <SectionHeading
          eyebrow="MY WATCH"
          title={
            <span>
              <StarFilled className="ad-icon-accent" /> 我的关注
            </span>
          }
        />

        {/* Daily lesson — front and center, above favorites */}
        <DailyLesson />

        <div style={{ marginTop: 'var(--space-5)' }}>
          <ResponsiveGrid cols={2} gap="lg">
            {/* Favorites panel */}
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

            {/* Pools + favorites news stacked */}
            <div className="dashboard-side-stack">
              {/* Favorites news — directly relevant to My Watch */}
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

              {/* Pools quick access */}
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
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════
          ZONE 3: 发现机会 (DISCOVER)
          Relaxed spacing — designed for reading and exploration.
          Answers: "What should I pay attention to?"
          ═══════════════════════════════════════════════════════════ */}
      <section className="dashboard-section dashboard-zone dashboard-zone--discover">
        <SectionHeading
          eyebrow="DISCOVER"
          title={
            <span>
              <FireOutlined className="ad-icon-accent" /> 发现机会
            </span>
          }
        />

        {/* Scores + Hot News side by side */}
        <ResponsiveGrid cols={2} gap="lg">
          {/* Score rankings — Top 10 */}
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

          {/* Hot news */}
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
        </ResponsiveGrid>

        {/* Data health card — placed below the main content in Discover */}
        <div style={{ marginTop: 'var(--space-5)' }}>
          <EtfHoldingsCoverageCard />
        </div>
      </section>

      {/* ── Platform KPI footer: subtle meta-stats row ── */}
      <section className="dashboard-section" style={{ marginTop: 'var(--space-7)' }}>
        <SectionHeading title="平台概览" />
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
    </PageShell>
  );
}
