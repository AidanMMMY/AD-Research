import './command-center.css';

import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Skeleton } from 'antd';
import { GlobalOutlined } from '@ant-design/icons';
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
import { codeToRegion } from '../../utils/macroRegion';
import EmptyState from '@/components/EmptyState';
import ReturnTag from '@/components/ReturnTag';
import { useSettingsStore } from '@/stores/settings';
import { usePriceStream } from '@/hooks/usePriceStream';
import { useMarketStream } from '@/hooks/useMarketStream';
import type { NewsArticle } from '@/types/news';
import {
  useFundFlowMarket,
  useFundFlowSignals,
  useFundFlowEtf,
  sortField,
} from '@/api/fundFlow';

function formatRelative(iso: string): string {
  return formatRelativeTz(iso, { withTimeAfterDays: 7 });
}

/**
 * Global index tile definitions for the compact Pulse strip.
 * Each tile maps to a macro code resolved via useMacroLatest.
 */
interface GroupTileDef {
  code: string;
  title: string;
  unit: string;
  type: 'macro' | 'realtime';
}

interface GroupDef {
  key: string;
  label: string;
  tiles: GroupTileDef[];
}

const PULSE_GROUPS: GroupDef[] = [
  {
    key: 'us_equity',
    label: '美股',
    tiles: [
      { code: 'global_sp500', title: '标普 500', unit: '', type: 'macro' },
      { code: 'global_nasdaq', title: '纳斯达克', unit: '', type: 'macro' },
      { code: 'global_dow', title: '道琼斯', unit: '', type: 'macro' },
      { code: 'SPY.US', title: 'SPY', unit: '', type: 'realtime' },
    ],
  },
  {
    key: 'us_bonds_fx',
    label: '美债/汇率',
    tiles: [
      { code: 'us_dgs10', title: 'US 10Y', unit: '%', type: 'macro' },
      { code: 'usd_cny', title: 'USD/CNY', unit: '', type: 'macro' },
      { code: 'usd_eur', title: 'USD/EUR', unit: '', type: 'macro' },
      { code: 'us_t10y3m', title: 'T10Y3M', unit: '%', type: 'macro' },
    ],
  },
  {
    key: 'asia_pacific',
    label: '亚太',
    tiles: [
      { code: 'global_shcomp', title: '上证', unit: '', type: 'macro' },
      { code: 'global_hsi', title: '恒生', unit: '', type: 'macro' },
      { code: 'global_n225', title: '日经', unit: '', type: 'macro' },
      { code: 'global_szse', title: '深证', unit: '', type: 'macro' },
      { code: 'global_kospi', title: 'KOSPI', unit: '', type: 'macro' },
      { code: '510300.SH', title: '沪深300ETF', unit: '', type: 'realtime' },
      { code: '159915.SZ', title: '创业板ETF', unit: '', type: 'realtime' },
    ],
  },
  {
    key: 'europe',
    label: '欧洲',
    tiles: [
      { code: 'global_ftse', title: 'FTSE 100', unit: '', type: 'macro' },
      { code: 'global_dax', title: 'DAX', unit: '', type: 'macro' },
      { code: 'global_cac', title: 'CAC 40', unit: '', type: 'macro' },
    ],
  },
  {
    key: 'crypto',
    label: '加密',
    tiles: [
      { code: 'BTC.US', title: 'BTC', unit: '', type: 'realtime' },
    ],
  },
];

function formatTileValue(v: number | null | undefined, unit: string): string {
  if (v == null || Number.isNaN(v)) return '—';
  if (unit === '%') return `${v.toFixed(2)}%`;
  if (Math.abs(v) >= 1000)
    return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return v.toFixed(2);
}

/** Page-local money formatter — 万 / 亿. */
function formatSignedMoney(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  const abs = Math.abs(v);
  const sign = v < 0 ? '-' : '';
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)} 亿`;
  if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(2)} 万`;
  return `${sign}${abs.toFixed(2)}`;
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

/** 为全球资产脉搏卡片聚合宏观/实时行情数据。 */
function useGlobalPulseData() {
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

  const INDEX_CODES = ['510300.SH', '159915.SZ', 'SPY.US', 'BTC.US'];
  const { prices } = usePriceStream(INDEX_CODES);
  const { latest: marketLatest } = useMarketStream(INDEX_CODES);

  const lookup = useMemo(() => {
    type LookupEntry = { value: number | null; change_pct: number | null };
    const map = new Map<string, LookupEntry>();
    for (const it of latestGlobal?.items ?? []) {
      map.set(it.code, { value: it.value ?? null, change_pct: it.change_pct ?? null });
    }
    for (const it of latestUs?.items ?? []) {
      if (!map.has(it.code)) {
        map.set(it.code, { value: it.value ?? null, change_pct: it.change_pct ?? null });
      }
    }
    for (const it of rtGlobal?.items ?? []) {
      const code = it.code as string;
      map.set(code, {
        value: (it.value as number) ?? null,
        change_pct: (it.change_pct as number) ?? null,
      });
    }
    return map;
  }, [latestGlobal, latestUs, rtGlobal]);

  const isLoading = gLoading || uLoading || rtLoading;

  const groups = useMemo(() => {
    return PULSE_GROUPS.map((g) => ({
      key: g.key,
      label: g.label,
      tiles: g.tiles.map((tile) => {
        let value: number | null = null;
        let change: number | null = null;
        if (tile.type === 'macro') {
          const entry = lookup.get(tile.code);
          value = entry?.value ?? null;
          change = entry?.change_pct ?? null;
        } else {
          const tick = marketLatest[tile.code] ?? (prices[tile.code] ? { ...prices[tile.code], ts: 0 } : undefined);
          value = tick?.price ?? null;
          change = tick?.change_pct ?? null;
        }
        return {
          code: tile.code,
          title: tile.title,
          value,
          change,
          unit: tile.unit,
          type: tile.type,
        };
      }),
    }));
  }, [lookup, marketLatest, prices]);

  return { groups, isLoading };
}

function useFundFlowCardData() {
  const { data: market, isLoading: mLoading } = useFundFlowMarket();
  const { data: signals = [], isLoading: sLoading } = useFundFlowSignals({
    sort: sortField('composite_score'),
    limit: 1,
  });
  const { data: etfList = [], isLoading: eLoading } = useFundFlowEtf({
    sort: sortField('premium_rate', 'desc'),
    limit: 1,
  });

  const shMain = market?.sh_main_net_inflow ?? null;
  const szMain = market?.sz_main_net_inflow ?? null;
  const total = shMain != null && szMain != null ? shMain + szMain : (shMain ?? szMain ?? null);
  const totalPct =
    market?.total_main_net_pct ??
    (market?.sh_main_net_pct != null && market?.sz_main_net_pct != null
      ? market.sh_main_net_pct + market.sz_main_net_pct
      : null);

  return {
    total,
    totalPct,
    topSignal: signals[0],
    topEtf: etfList[0],
    isLoading: (mLoading && !market) || (sLoading && signals.length === 0) || (eLoading && etfList.length === 0),
  };
}

/** 提取评分数据作为动量/信号卡片的数据源。 */
function useScoreMomentum(limit = 5) {
  const { data: scoresData } = useScores({ limit });
  return scoresData?.items || [];
}

/** 生成信号流数据：资金流 Top3 + 热点新闻。 */
function useSignalStream() {
  const { data: signals = [] } = useFundFlowSignals({
    sort: sortField('composite_score'),
    limit: 3,
  });
  const { data: hotNews = [] } = useQuery({
    queryKey: ['dashboard-hot-news'],
    queryFn: () => newsApi.list({ importance_min: 3, page: 1, page_size: 4 }).then((r) => r.data.items),
    staleTime: 60_000,
  });
  return { signals, hotNews };
}

export default function Dashboard() {
  const navigate = useNavigate();
  const mode = useSettingsStore((s) => s.mode);
  const { favorites, count: favCount, isLoading: favLoading } = useFavorites(6);
  const { data: pools } = usePoolList();
  const statsKpis = useDashboardStatsKpis();
  const { groups: pulseGroups, isLoading: pulseLoading } = useGlobalPulseData();
  const { total, totalPct, topSignal, topEtf, isLoading: ffLoading } = useFundFlowCardData();
  const momentum = useScoreMomentum(5);
  const { signals, hotNews } = useSignalStream();

  const favCodes = useMemo(() => (favorites || []).map((f: any) => f.etf_code), [favorites]);
  const { prices: favPrices } = usePriceStream(favCodes);
  const { latest: favMarketLatest } = useMarketStream(favCodes);

  const now = new Date();
  const timeString = now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  const dateString = now.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' });

  const navItems = [
    { label: '指挥中心', path: '/', active: true },
    { label: '全球市场', path: '/global' },
    { label: '板块轮动', path: '/sector-rotation' },
    { label: '资金流', path: '/fund-flow' },
    { label: '自选股', path: '/favorites' },
    { label: '标的池', path: '/pools' },
    { label: '新闻', path: '/news' },
    { label: '研究', path: '/learning' },
  ];

  const maxScore = Math.max(1, ...momentum.map((s: any) => s.composite_score ?? 0));

  const formatChange = (v: number | null | undefined) => {
    if (v == null || Number.isNaN(v)) return '—';
    return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
  };

  const changeColor = (v: number | null | undefined) => {
    if (v == null) return 'var(--cc-text2)';
    return v >= 0 ? 'var(--cc-rise)' : 'var(--cc-fall)';
  };

  return (
    <div className="dashboard-command-center">
      <header className="cc-topbar">
        <div className="cc-topbar__brand">
          <div className="cc-topbar__logo">AD</div>
          <div className="cc-topbar__title">
            <span className="cc-topbar__name">AD-Research</span>
            <span className="cc-topbar__subtitle">市场指挥中心</span>
          </div>
        </div>
        <div className="cc-topbar__search">
          <input
            className="cc-topbar__search-input"
            type="search"
            placeholder="搜索标的、新闻、研报…"
            aria-label="搜索标的"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                const q = e.currentTarget.value.trim();
                if (q) navigate(`/instruments?q=${encodeURIComponent(q)}`);
              }
            }}
          />
        </div>
        <div className="cc-topbar__pulse">
          <span className="cc-topbar__pulse-label">PULSE</span>
          <div className="cc-pulse-bars">
            {[14, 22, 18, 28, 20, 24, 16].map((h, i) => (
              <span
                key={i}
                className="cc-pulse-bar"
                style={{ height: `${h}px`, background: i === 3 ? 'var(--cc-accent)' : 'var(--cc-border-glow)' }}
              />
            ))}
          </div>
        </div>
        <div className="cc-topbar__status">
          <span className="cc-status-dot" />
          <span>实时连接</span>
          <span className="cc-status-time">{dateString} {timeString}</span>
        </div>
      </header>

      <div className="cc-layout">
        <aside className="cc-sidebar" aria-label="主导航">
          {navItems.map((item) => (
            <div
              key={item.path}
              className={`cc-nav-item ${item.active ? 'cc-nav-item--active' : ''}`}
              onClick={() => navigate(item.path)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  navigate(item.path);
                }
              }}
            >
              <span className="cc-nav-icon" aria-hidden />
              {item.label}
            </div>
          ))}
          <div className="cc-user-card">
            <div className="cc-user-name">研究员</div>
            <div className="cc-user-mode">{mode === 'pro' ? '专业模式' : '标准模式'}</div>
          </div>
        </aside>

        <main className="cc-main">
          <header className="cc-header">
            <div className="cc-header__eyebrow">MARKET COMMAND CENTER</div>
            <h1 className="cc-header__title">市场指挥中心</h1>
          </header>

          {/* Global Pulse */}
          <section className="cc-pulse-grid" aria-label="全球资产脉搏">
            <div className="cc-pulse-grid__header">
              <GlobalOutlined style={{ color: 'var(--cc-muted)', fontSize: 12 }} />
              <span className="cc-pulse-grid__title">全球资产脉搏</span>
            </div>
            <div className="cc-pulse-groups">
              {pulseGroups.map((group) => (
                <div key={group.key} className="cc-pulse-group">
                  <div className="cc-pulse-group__label">{group.label}</div>
                  <div className="cc-pulse-group__tiles">
                    {group.tiles.map((tile) => {
                      const change = tile.change;
                      return (
                        <div
                          key={tile.code}
                          className="cc-pulse-item"
                          role="button"
                          tabIndex={0}
                          onClick={() =>
                            navigate(
                              tile.type === 'realtime'
                                ? `/instruments/${tile.code}`
                                : `/macro?region=${codeToRegion(tile.code)}&code=${encodeURIComponent(tile.code)}`
                            )
                          }
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              navigate(
                                tile.type === 'realtime'
                                  ? `/instruments/${tile.code}`
                                  : `/macro?region=${codeToRegion(tile.code)}&code=${encodeURIComponent(tile.code)}`
                              );
                            }
                          }}
                        >
                          <span className="cc-pulse-item__code">{tile.title}</span>
                          <span className="cc-pulse-item__value">
                            {pulseLoading && !tile.value ? '—' : formatTileValue(tile.value, tile.unit)}
                          </span>
                          <span className="cc-pulse-item__change" style={{ color: changeColor(change) }}>
                            {formatChange(change)}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <div className="cc-grid">
            {/* Fund Flow */}
            <section className="cc-card">
              <div className="cc-card__header">
                <div>
                  <div className="cc-card__title">资金流</div>
                  <div className="cc-card__subtitle">A股 大盘主力净流入</div>
                </div>
                <span className="cc-card__extra" onClick={() => navigate('/fund-flow')} role="button" tabIndex={0}>
                  监控 →
                </span>
              </div>
              <div className="cc-fund-flow__total">
                <span className="cc-fund-flow__value">
                  {ffLoading || total == null ? '—' : formatSignedMoney(total)}
                </span>
                <span className="cc-fund-flow__unit">元</span>
              </div>
              <div className="cc-fund-flow__pct" style={{ color: changeColor(totalPct) }}>
                {formatChange(totalPct)}
              </div>

              {topSignal && (
                <div className="cc-flow-item">
                  <div className="cc-flow-item__header">
                    <span className="cc-flow-item__label">综合信号 Top1 · {topSignal.ts_code}</span>
                    <span className="cc-flow-item__value" style={{ color: 'var(--cc-accent)' }}>
                      {topSignal.composite_score?.toFixed(2) ?? '—'}
                    </span>
                  </div>
                  <div className="cc-flow-bar">
                    <div
                      className="cc-flow-bar__fill"
                      style={{
                        width: `${Math.min(100, (topSignal.composite_score ?? 0))}%`,
                        background: 'var(--cc-accent)',
                      }}
                    />
                  </div>
                </div>
              )}

              {topEtf && (
                <div className="cc-flow-item">
                  <div className="cc-flow-item__header">
                    <span className="cc-flow-item__label">ETF 折溢价 Top1 · {topEtf.ts_code}</span>
                    <span className="cc-flow-item__value" style={{ color: changeColor(topEtf.premium_rate) }}>
                      {formatChange(topEtf.premium_rate)}
                    </span>
                  </div>
                  <div className="cc-flow-bar">
                    <div
                      className="cc-flow-bar__fill"
                      style={{
                        width: `${Math.min(100, Math.abs(topEtf.premium_rate ?? 0) * 10)}%`,
                        background: changeColor(topEtf.premium_rate),
                      }}
                    />
                  </div>
                </div>
              )}
            </section>

            {/* Sector / Momentum */}
            <section className="cc-card">
              <div className="cc-card__header">
                <div>
                  <div className="cc-card__title">动量聚焦</div>
                  <div className="cc-card__subtitle">综合评分最高的标的</div>
                </div>
                <span className="cc-card__extra" onClick={() => navigate('/scores')} role="button" tabIndex={0}>
                  评分 →
                </span>
              </div>
              <div className="cc-sector-header">
                <span>排名</span>
                <span>标的</span>
                <span>动量</span>
                <span>评分</span>
              </div>
              {momentum.map((s: any, idx: number) => {
                const score = s.composite_score ?? 0;
                const ret = s.return_1m ?? 0;
                return (
                  <div
                    key={s.etf_code}
                    className="cc-sector-row"
                    onClick={() => navigate(`/instruments/${s.etf_code}`)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        navigate(`/instruments/${s.etf_code}`);
                      }
                    }}
                  >
                    <span className="cc-sector-row__rank">{idx + 1}</span>
                    <span className="cc-sector-row__name">
                      {s.etf_code}
                    </span>
                    <div className="cc-sector-row__bar">
                      <div
                        className="cc-sector-row__bar-fill"
                        style={{
                          width: `${(score / maxScore) * 100}%`,
                          background: ret >= 0 ? 'var(--cc-rise)' : 'var(--cc-fall)',
                        }}
                      />
                    </div>
                    <span className="cc-sector-row__mom">
                      <ReturnTag value={s.return_1m} />
                    </span>
                    <span className="cc-sector-row__score">{score.toFixed(1)}</span>
                  </div>
                );
              })}
            </section>

            {/* Signal Stream */}
            <section className="cc-card">
              <div className="cc-card__header">
                <div>
                  <div className="cc-card__title">信号流</div>
                  <div className="cc-card__subtitle">实时资金与事件信号</div>
                </div>
                <span className="cc-card__extra" onClick={() => navigate('/fund-flow')} role="button" tabIndex={0}>
                  全部 →
                </span>
              </div>
              {signals.slice(0, 3).map((sig: any, i: number) => (
                <div
                  key={sig.ts_code || i}
                  className="cc-signal"
                  onClick={() => sig.ts_code && navigate(`/instruments/${sig.ts_code}`)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if ((e.key === 'Enter' || e.key === ' ') && sig.ts_code) {
                      e.preventDefault();
                      navigate(`/instruments/${sig.ts_code}`);
                    }
                  }}
                >
                  <span className="cc-signal__time">{sig.ts_code}</span>
                  <span className="cc-signal__badge" style={{ color: 'var(--cc-accent)' }}>资金</span>
                  <div>
                    <div className="cc-signal__code">综合评分 {sig.composite_score?.toFixed(2) ?? '—'}</div>
                    <div className="cc-signal__desc">{sig.signal_name || '资金流综合信号'}</div>
                  </div>
                  <span className="cc-signal__score" style={{ color: 'var(--cc-accent)' }}>
                    {sig.composite_score?.toFixed(1) ?? '—'}
                  </span>
                </div>
              ))}
              {hotNews.slice(0, 2).map((article: NewsArticle) => (
                <div
                  key={`news-${article.id}`}
                  className="cc-signal"
                  onClick={() => navigate(`/news/${article.id}`)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      navigate(`/news/${article.id}`);
                    }
                  }}
                >
                  <span className="cc-signal__time">{formatRelative(article.published_at)}</span>
                  <span className="cc-signal__badge" style={{ color: 'var(--cc-warn)' }}>事件</span>
                  <div>
                    <div className="cc-signal__code" style={{ fontWeight: 500 }}>
                      {article.title}
                    </div>
                    <div className="cc-signal__desc">{article.source}</div>
                  </div>
                  <span className="cc-signal__score" style={{ color: 'var(--cc-warn)', fontSize: 11 }}>
                    {article.importance ?? '—'}
                  </span>
                </div>
              ))}
            </section>
          </div>

          <div className="cc-grid cc-grid--bottom">
            {/* Watchlist */}
            <section className="cc-card">
              <div className="cc-card__header">
                <div>
                  <div className="cc-card__title">自选股</div>
                  <div className="cc-card__subtitle">{favCount} 只关注标的</div>
                </div>
                <span className="cc-card__extra" onClick={() => navigate('/favorites')} role="button" tabIndex={0}>
                  管理 →
                </span>
              </div>
              <div className="cc-watch-header">
                <span>标的</span>
                <span>价格</span>
                <span>涨跌</span>
                <span>评分</span>
              </div>
              {favLoading ? (
                <Skeleton active paragraph={{ rows: 4 }} />
              ) : favCount === 0 ? (
                <EmptyState title="暂无自选股" description="在详情页点击 ★ 加入自选" />
              ) : (
                favorites.slice(0, 6).map((item: any) => {
                  const tick = favMarketLatest[item.etf_code] ?? favPrices[item.etf_code];
                  const price = tick?.price;
                  const change = tick?.change_pct;
                  const score = item.composite_score ?? 0;
                  return (
                    <div
                      key={item.etf_code}
                      className="cc-watch-row"
                      onClick={() => navigate(`/instruments/${item.etf_code}`)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          navigate(`/instruments/${item.etf_code}`);
                        }
                      }}
                    >
                      <div>
                        <div className="cc-watch-row__code">{item.etf_code}</div>
                        <div className="cc-watch-row__name">{item.etf_name}</div>
                      </div>
                      <span className="cc-watch-row__price">
                        {price != null ? price.toFixed(price >= 100 ? 2 : 3) : '—'}
                      </span>
                      <span className="cc-watch-row__change" style={{ color: changeColor(change) }}>
                        {formatChange(change)}
                      </span>
                      <span className="cc-watch-row__score">{score ? Math.round(score) : '—'}</span>
                    </div>
                  );
                })
              )}
            </section>

            {/* News Briefing */}
            <section className="cc-card">
              <div className="cc-card__header">
                <div>
                  <div className="cc-card__title">要闻速递</div>
                  <div className="cc-card__subtitle">今日重要资讯</div>
                </div>
                <span className="cc-card__extra" onClick={() => navigate('/news')} role="button" tabIndex={0}>
                  新闻 →
                </span>
              </div>
              {!hotNews || hotNews.length === 0 ? (
                <EmptyState title="暂无重要资讯" />
              ) : (
                hotNews.slice(0, 4).map((article: NewsArticle, idx: number) => (
                  <div
                    key={article.id}
                    className="cc-brief"
                    onClick={() => navigate(`/news/${article.id}`)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        navigate(`/news/${article.id}`);
                      }
                    }}
                  >
                    <span className="cc-brief__rank">{idx + 1}</span>
                    <div>
                      <div className="cc-brief__title">{article.title}</div>
                      <div className="cc-brief__desc">
                        {article.source} · {(article.symbols ?? []).slice(0, 3).map((s) => s.symbol).join(', ')}
                      </div>
                    </div>
                    <span className="cc-brief__time">{formatRelative(article.published_at)}</span>
                  </div>
                ))
              )}
            </section>

            {/* Decision Queue */}
            <section className="cc-card">
              <div className="cc-card__header">
                <div>
                  <div className="cc-card__title">决策队列</div>
                  <div className="cc-card__subtitle">平台数据与覆盖概览</div>
                </div>
              </div>
              <div className="cc-decision">
                <span className="cc-decision__label">标的总数</span>
                <span className="cc-decision__value">{statsKpis.etf.toLocaleString()}</span>
              </div>
              <div className="cc-decision">
                <span className="cc-decision__label">评分覆盖</span>
                <span className="cc-decision__value" style={{ color: 'var(--cc-accent)' }}>
                  {statsKpis.score.toLocaleString()}
                </span>
              </div>
              <div className="cc-decision">
                <span className="cc-decision__label">分类数</span>
                <span className="cc-decision__value">{statsKpis.category.toLocaleString()}</span>
              </div>
              <div className="cc-decision">
                <span className="cc-decision__label">标的池</span>
                <span className="cc-decision__value" style={{ color: 'var(--cc-warn)' }}>
                  {pools?.length ?? 0}
                </span>
              </div>
            </section>
          </div>

          <footer className="cc-footer">
            <span className="cc-footer__dot" />
            <span>系统运行正常</span>
            <span className="cc-footer__meta">
              {statsKpis.etf.toLocaleString()} 标的 · {statsKpis.score.toLocaleString()} 评分 · 更新于{' '}
              {statsKpis.updatedAt ? formatDateTime(new Date(statsKpis.updatedAt).toISOString()) : '—'}
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}
