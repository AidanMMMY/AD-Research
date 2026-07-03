import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, List, Spin, Skeleton, Tag, Badge, Tooltip, Space } from 'antd';
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
import { useQuery } from '@tanstack/react-query';
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
import ResponsiveGrid from '@/components/ResponsiveGrid';
import SectionHeading from '@/components/SectionHeading';
import StatCard from '@/components/StatCard';
import EmptyState from '@/components/EmptyState';
import Panel from '@/components/Panel';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import ReturnTag from '@/components/ReturnTag';
import ScoreBar from '@/components/ScoreBar';
import TickerTape from '@/components/TickerTape';
import HelpPopover from '@/components/HelpPopover';
import DailyLesson from '@/components/DailyLesson';
import { useLearnStats } from '@/hooks/useLearnedTerms';
import { useSettingsStore } from '@/stores/settings';
import { usePriceStream } from '@/hooks/usePriceStream';
import { useMarketStream } from '@/hooks/useMarketStream';
import type { NewsArticle, SentimentLabel } from '@/types/news';

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
          <Tag key={`${s.symbol}-${s.match_type}`} className="dashboard-news-row__tag">
            <InstrumentCodeTag code={s.symbol} name={s.name ?? undefined} name_zh={s.name_zh} />
          </Tag>
        ))}
        <span className="dashboard-news-row__spacer" />
        {article.sentiment_label && (
          <Badge
            color={SENTIMENT_COLORS[article.sentiment_label]}
            text={
              <span
                className="dashboard-news-row__sentiment"
                style={{ color: SENTIMENT_COLORS[article.sentiment_label] }}
              >
                {SENTIMENT_LABELS[article.sentiment_label]}
              </span>
            }
          />
        )}
      </div>
    </div>
  );
}

/**
 * Top-of-dashboard "全球速览" — pulls 4 headline overseas indicators
 * from the Macro API (FRED-backed):
 *   - 美 10Y Treasury yield  (us_dgs10)
 *   - VIX 恐慌指数           (us_vix)
 *   - 美元指数(广义)         (global_dxy)
 *   - 布伦特原油            (global_brent)
 *
 * Backed by the same MacroIndicator rows written by FredService; the
 * section degrades gracefully when no data has been ingested yet.
 */
const GLOBAL_TILES: Array<{
  code: string;
  title: string;
  unit: string;
}> = [
  { code: 'us_dgs10', title: '美 10Y 国债', unit: '%' },
  { code: 'us_vix', title: 'VIX 恐慌指数', unit: '' },
  { code: 'global_dxy', title: '美元指数(广义)', unit: '' },
  { code: 'global_brent', title: '布伦特原油', unit: 'USD/桶' },
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
    const map = new Map<string, { value: number | null; period: string | null }>();
    for (const it of latestGlobal?.items ?? []) {
      map.set(it.code, { value: it.value ?? null, period: it.period ?? null });
    }
    for (const it of latestUs?.items ?? []) {
      if (!map.has(it.code)) {
        map.set(it.code, { value: it.value ?? null, period: it.period ?? null });
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
              <div
                key={tile.code}
                role="button"
                tabIndex={0}
                onClick={() => navigate('/global')}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    navigate('/global');
                  }
                }}
                className="dashboard-index-card dashboard-index-card--clickable"
              >
              <Panel
                variant="default"
                padding="md"
                className="dashboard-index-card"
              >
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
                  {entry?.period ? (
                    <span className="dashboard-index-card__timestamp">
                      {entry.period}
                    </span>
                  ) : null}
                </div>
              </Panel>
              </div>
            );
          })}
        </ResponsiveGrid>
      )}
    </section>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const mode = useSettingsStore((s) => s.mode);
  const learnStats = useLearnStats();
  const { data: scoresData } = useScores({ limit: 10 });
  const { favorites, count: favCount, isLoading: favLoading } = useFavorites(10);
  const { data: pools, isLoading: poolsLoading } = usePoolList();
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['stats-overview'],
    queryFn: () => statsApi.overview().then((r) => r.data),
    staleTime: 60_000,
  });

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
  const { latest: marketLatest, isConnected: marketConnected } = useMarketStream(INDEX_CODES);

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
  ];

  return (
    <PageShell maxWidth="full" className="dashboard-shell">
      <TickerTape limit={20} />
      <header className="masthead" data-onboard="welcome-dashboard">
        <div className="masthead-dateline">
          AD-RESEARCH ·{' '}
          {new Date().toLocaleDateString('zh-CN', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
          })}{' '}
          · A股全市场综述
        </div>
        <h1 className="display-heading masthead-title">首页看板</h1>
        <p className="masthead-kicker">
          综合评分 · 收藏 · 标的池概览 · {new Date().toISOString().slice(0, 10)}
        </p>
      </header>

      {/* M26: consolidated quick-actions bar. K14 (learning) + K16
          (portfolio) + M20 (knowledge graph) chips are merged into one
          bar with inline dividers, replacing the previous "3 stacked
          chip rows" layout that dominated the page top. */}
      <section className="dashboard-quick-actions" aria-label="快捷入口">
        <Space size={[8, 8]} wrap className="dashboard-quick-actions__row">
          <span className="dashboard-quick-actions__group">
            <span className="dashboard-quick-actions__label">新手教程</span>
            <Tag
              icon={<BookOutlined />}
              color="blue"
              className="dashboard-learning-chip"
              onClick={() => navigate('/learning')}
            >
              总览
            </Tag>
            <Tag
              icon={<LineChartOutlined />}
              color="cyan"
              className="dashboard-learning-chip"
              onClick={() => navigate('/learning')}
            >
              如何看估值
            </Tag>
            <Tag
              icon={<ExperimentOutlined />}
              color="purple"
              className="dashboard-learning-chip"
              onClick={() => navigate('/learning')}
            >
              如何做回测
            </Tag>
          </span>

          <span className="dashboard-quick-actions__divider" aria-hidden="true" />

          <span className="dashboard-quick-actions__group">
            <span className="dashboard-quick-actions__label">组合中心</span>
            <Tag
              icon={<WalletOutlined />}
              color="gold"
              className="dashboard-learning-chip"
              onClick={() => navigate('/portfolio')}
              title="查看投资组合中心（模拟账户 / 真实账户 / 目标 Pool diff 聚合）"
            >
              我的组合
            </Tag>
            <Tag
              icon={<DollarOutlined />}
              color="geekblue"
              className="dashboard-learning-chip"
              onClick={() => navigate('/paper-trading')}
              title="新建或切换模拟账户"
            >
              模拟账户
            </Tag>
            <Tag
              icon={<ThunderboltOutlined />}
              color="magenta"
              className="dashboard-learning-chip"
              onClick={() => navigate('/live-trading')}
              title="查看真实交易配置与持仓（Binance testnet/mainnet）"
            >
              真实账户
            </Tag>
            <Tag
              icon={<AppstoreOutlined />}
              color="default"
              className="dashboard-learning-chip"
              onClick={() => navigate('/pools')}
              title="管理中长期目标组合（与组合中心不同：这里是目标权重，不是实际持仓）"
            >
              标的池
            </Tag>
          </span>

          <span className="dashboard-quick-actions__divider" aria-hidden="true" />

          <span className="dashboard-quick-actions__group">
            <span className="dashboard-quick-actions__label">知识图谱</span>
            <Tag
              icon={<PartitionOutlined />}
              color="volcano"
              className="dashboard-learning-chip"
              onClick={() => navigate('/learning?panel=terms')}
              title="查看全部术语词条（M20 速查面板入口；P2 升级为图谱视图）"
            >
              查看知识图谱
            </Tag>
          </span>

          {learnStats.total > 0 && (
            <span className="dashboard-quick-actions__meta">
              本周已学 {learnStats.total} 个术语
            </span>
          )}
        </Space>
      </section>

      {/* M26: KPI strip + DailyLesson side-by-side. On desktop the four
          StatCards occupy the left 4-col strip while DailyLesson fills
          the right column; on tablet/mobile they stack. This replaces
          the previous full-width-lesson + below-row KPI flow that left
          DailyLesson stranded above the metrics. */}
      <section className="dashboard-section dashboard-kpi-row">
        <ResponsiveGrid cols={4} gap="md" className="dashboard-kpi-row__stats">
          {[
            { title: '标的总数', value: stats?.etf_count ?? 0, suffix: undefined, onClick: () => navigate('/instruments'), term: 'etf' },
            { title: '评分覆盖', value: stats?.score_count ?? 0, suffix: `/ ${stats?.etf_count ?? 0}`, onClick: () => navigate('/scores'), term: 'composite_score' },
            { title: '分类数', value: stats?.category_count ?? 0, suffix: undefined, onClick: undefined, term: 'rank_category' },
            { title: '评分模板', value: stats?.template_count ?? 0, suffix: undefined, onClick: () => navigate('/scores'), term: 'strategy_template' },
          ].map((item) => (
            <StatCard
              key={item.title}
              title={item.title}
              value={item.value}
              suffix={item.suffix}
              loading={statsLoading}
              onClick={item.onClick}
              term={item.term}
            />
          ))}
        </ResponsiveGrid>
        <div className="dashboard-kpi-row__lesson">
          {learnStats.total > 0 && (
            <span
              className="daily-lesson-week-badge"
              data-testid="dashboard-week-learned-badge"
              aria-label={`本周已学 ${learnStats.thisWeekApprox} 个术语`}
            >
              本周已学 {learnStats.thisWeekApprox} 个术语
            </span>
          )}
          <DailyLesson />
        </div>
      </section>

      {/* ── Global markets snapshot (P0: 2026-07-04) ─────────────────── */}
      <GlobalSnapshot />

      <section className="dashboard-section">
        <SectionHeading title="实时行情" />
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

      {/* News row: hot news + favorites news */}
      <ResponsiveGrid cols={2} gap="lg" className="dashboard-section">
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

      <ResponsiveGrid cols={2} gap="lg" className="dashboard-score-grid dashboard-section">
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
            title="我的收藏"
            extra={
              favCount > 0 ? (
                <span className="panel-extra-link" onClick={() => navigate('/instruments')}>
                  查看全部 →
                </span>
              ) : undefined
            }
          >
            {favLoading ? (
              <div className="ad-text-center ad-py-7">
                <Spin />
              </div>
            ) : favCount === 0 ? (
              <EmptyState
                title="暂无收藏的标的"
                description="在详情页点击收藏，这里会显示你关注的标的"
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
              <div className="ad-text-center ad-py-7">
                <Spin />
              </div>
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
    </PageShell>
  );
}
