import { useState, useMemo, useEffect, useRef, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Input,
  Segmented,
  Skeleton,
  Tooltip,
  Select,
  message,
  Space,
  Alert,
  Button,
} from 'antd';
import {
  SearchOutlined,
  HeartOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  FireOutlined,
} from '@ant-design/icons';
import { newsApi } from '@/api/news';
import type {
  NewsArticle,
  NewsMarket,
  SentimentLabel,
  ImportanceLevel,
} from '@/types/news';
import { SENTIMENT_LABELS } from '@/utils/sentiment';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import Panel from '@/components/Panel';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import EmptyState from '@/components/EmptyState';
import Sparkline from '@/components/Sparkline';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import HelpPopover from '@/components/HelpPopover';
import ThemeTag from '@/components/ThemeTag';
import { useSettingsStore } from '@/stores/settings';
import './styles.css';

/**
 * Apple-style motion layer (scoped to this page):
 * - Response: feedback lands on pointer-down (:active, 0ms), release springs back.
 * - Springs: critically-damped-ish cubic-bezier; transform-only for frame smoothness.
 * - Direct manipulation: tappable cells advertise pressability via touch-action
 *   and a scale press, telegraphing the selection destination (hint direction).
 * - Typography: size-specific tracking (large tight, small loose).
 * - Reduced motion: cross-fade only, transforms disabled.
 */
const ADX_STYLE = `
.adx-sentiment {
  --adx-spring: cubic-bezier(0.5, 1.6, 0.3, 1);
  --adx-ease-out: cubic-bezier(0.22, 0.9, 0.3, 1);
}
.adx-sentiment .ant-btn,
.adx-sentiment .ad-heatmap-cell,
.adx-sentiment .ad-mover-row {
  touch-action: manipulation;
  transition: transform 240ms var(--adx-spring), background-color 140ms var(--adx-ease-out), box-shadow 140ms var(--adx-ease-out);
}
.adx-sentiment .ant-btn:active,
.adx-sentiment .ad-heatmap-cell:active,
.adx-sentiment .ad-mover-row:active {
  transform: scale(0.96);
  transition-duration: 0ms;
}
.adx-sentiment .ad-heatmap-cell:hover,
.adx-sentiment .ad-mover-row:hover {
  will-change: transform;
}
.adx-sentiment .ant-segmented-item {
  touch-action: manipulation;
  transition: color 140ms var(--adx-ease-out);
}
.adx-sentiment .ant-select-selector {
  transition: border-color 140ms var(--adx-ease-out), box-shadow 140ms var(--adx-ease-out);
}
.adx-sentiment h1,
.adx-sentiment h2,
.adx-sentiment .ant-typography h1,
.adx-sentiment .ant-typography h2 {
  letter-spacing: -0.02em;
  line-height: 1.18;
}
.adx-sentiment .ad-text-xs,
.adx-sentiment .ad-text-small {
  letter-spacing: 0.01em;
}
@media (prefers-reduced-motion: reduce) {
  .adx-sentiment *,
  .adx-sentiment *::before,
  .adx-sentiment *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }
  .adx-sentiment .ant-btn:active,
  .adx-sentiment .ad-heatmap-cell:active,
  .adx-sentiment .ad-mover-row:active {
    transform: none;
  }
}
`;

function AdxShell({ children }: { children: ReactNode }) {
  return (
    <div className="adx-sentiment">
      <style>{ADX_STYLE}</style>
      {children}
    </div>
  );
}

const MARKET_OPTIONS: { label: string; value: NewsMarket | 'all' }[] = [
  { label: '全部', value: 'all' },
  { label: 'A 股', value: 'cn_a' },
  { label: '美股', value: 'us' },
  { label: '加密', value: 'crypto' },
];

/**
 * Pie-slice colors for positive/neutral/negative sentiment. These use the
 * theme's market-color variables, which automatically flip between the China
 * (red up / green down) and US (green up / red down) conventions via the
 * `data-color-convention` attribute set by `useSettingsStore`.
 */
const POLL_SLICE_COLORS: Record<SentimentLabel, string> = {
  positive: 'var(--color-rise)',
  neutral: 'var(--text-tertiary)',
  negative: 'var(--color-fall)',
};

interface SymbolAggregate {
  symbol: string;
  market: string | null | undefined;
  count: number;
  /** Average sentiment score, weighted by importance. */
  score: number | null;
  label: SentimentLabel | null;
  /** Bull/bear ratio, normalized to sum=1. */
  bull: number;
  bear: number;
  neutral: number;
  /** Recent daily scores for sparkline (oldest -> newest). */
  sparkline: number[];
  /** Instrument display name (cached from ``etf_info``). */
  name?: string | null;
  /** Chinese display name (cached from ``etf_info``). */
  name_zh?: string | null;
}

const PAGE_SIZE = 100;

/**
 * Group articles by symbol, compute importance-weighted aggregate
 * sentiment, and produce per-day sparkline points.
 */
function aggregateBySymbol(articles: NewsArticle[]): SymbolAggregate[] {
  type Bucket = {
    symbol: string;
    market: string | null | undefined;
    articles: NewsArticle[];
    scoreSum: number;
    weightSum: number;
    bull: number;
    bear: number;
    neutral: number;
    name: string | null;
    name_zh: string | null;
  };

  const buckets = new Map<string, Bucket>();
  for (const a of articles) {
    for (const s of a.symbols) {
      const cur = buckets.get(s.symbol) ?? {
        symbol: s.symbol,
        market: s.market,
        articles: [] as NewsArticle[],
        scoreSum: 0,
        weightSum: 0,
        bull: 0,
        bear: 0,
        neutral: 0,
        name: s.name ?? null,
        name_zh: s.name_zh ?? null,
      };
      cur.articles.push(a);
      const w = a.importance ?? 3;
      if (a.sentiment_score != null) {
        cur.scoreSum += a.sentiment_score * w;
        cur.weightSum += w;
      }
      if (a.sentiment_label === 'positive') cur.bull += w;
      else if (a.sentiment_label === 'negative') cur.bear += w;
      else cur.neutral += w;
      buckets.set(s.symbol, cur);
    }
  }

  return Array.from(buckets.values()).map((b) => {
    const score = b.weightSum > 0 ? b.scoreSum / b.weightSum : null;
    let label: SentimentLabel | null = null;
    if (score != null) {
      if (score > 0.2) label = 'positive';
      else if (score < -0.2) label = 'negative';
      else label = 'neutral';
    }
    // Build per-day sparkline (last 14 days).
    const byDay = new Map<string, { sum: number; w: number }>();
    for (const a of b.articles) {
      if (a.sentiment_score == null) continue;
      const day = (a.published_at ?? '').slice(0, 10);
      if (!day) continue;
      const cur = byDay.get(day) ?? { sum: 0, w: 0 };
      const w = a.importance ?? 3;
      cur.sum += a.sentiment_score * w;
      cur.w += w;
      byDay.set(day, cur);
    }
    const sparkline = Array.from(byDay.entries())
      .sort(([a], [b]) => (a < b ? -1 : 1))
      .slice(-14)
      .map(([, v]) => (v.w > 0 ? v.sum / v.w : 0));
    return {
      symbol: b.symbol,
      market: b.market,
      name: b.name,
      name_zh: b.name_zh,
      count: b.articles.length,
      score,
      label,
      bull: b.bull,
      bear: b.bear,
      neutral: b.neutral,
      sparkline,
    };
  });
}

/**
 * Compute CSS custom properties for a heatmap cell background. Positive scores
 * use `--color-rise`, negative scores use `--color-fall`, and the alpha is
 * encoded in `--heatmap-intensity`. Because the color variables are flipped by
 * the active `data-color-convention`, the heatmap automatically follows the
 * user's China/US preference without hard-coding RGB values.
 */
function heatmapVars(
  score: number | null,
  importance: ImportanceLevel | null,
): React.CSSProperties {
  if (score == null) {
    return {
      '--heatmap-color': 'var(--bg-elevated)',
      '--heatmap-intensity': '1',
    } as React.CSSProperties;
  }
  const intensity = Math.min(1, Math.abs(score) * 1.4);
  const alpha = 0.15 + 0.55 * intensity * (importance != null ? importance / 5 : 0.5);
  return {
    '--heatmap-color': score > 0 ? 'var(--color-rise)' : 'var(--color-fall)',
    '--heatmap-intensity': alpha.toFixed(2),
  } as React.CSSProperties;
}

/** Compute pie-slice percentage paths for bull/bear/neutral breakdown. */
function PieBreakdown({ row }: { row: SymbolAggregate }) {
  const { ref, width } = useMeasuredWidth<HTMLDivElement>();
  const size = Math.max(48, Math.min(72, width || 56));
  const total = row.bull + row.bear + row.neutral;
  if (total === 0) {
    return <span className="ad-text-small ad-text-tertiary">—</span>;
  }
  const slices = [
    { label: '多', value: row.bull, color: POLL_SLICE_COLORS.positive },
    { label: '空', value: row.bear, color: POLL_SLICE_COLORS.negative },
    { label: '中', value: row.neutral, color: POLL_SLICE_COLORS.neutral },
  ];
  const r = size * 0.39;
  const cx = size / 2;
  const cy = size / 2;
  let acc = 0;
  return (
    <Tooltip
      title={
        <div className="ad-tooltip-list">
          <div>多 {(row.bull / total * 100).toFixed(0)}%</div>
          <div>空 {(row.bear / total * 100).toFixed(0)}%</div>
          <div>中 {(row.neutral / total * 100).toFixed(0)}%</div>
        </div>
      }
    >
      <div ref={ref} className="ad-sentiment-pie-breakdown">
        <svg width="100%" height="100%" viewBox={`0 0 ${size} ${size}`}>
          {slices.map((s) => {
            if (s.value === 0) return null;
            const start = (acc / total) * 2 * Math.PI;
            acc += s.value;
            const end = (acc / total) * 2 * Math.PI;
            const x1 = cx + r * Math.sin(start);
            const y1 = cy - r * Math.cos(start);
            const x2 = cx + r * Math.sin(end);
            const y2 = cy - r * Math.cos(end);
            const large = end - start > Math.PI ? 1 : 0;
            return (
              <path
                key={s.label}
                d={`M ${cx} ${cy} L ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} Z`}
                fill={s.color}
              />
            );
          })}
          <circle cx={cx} cy={cy} r={r * 0.45} fill="var(--card-bg)" />
        </svg>
      </div>
    </Tooltip>
  );
}

/** 5-axis radar: importance, count, bull ratio, score abs, freshness. */
function DistributionRadar({ row }: { row: SymbolAggregate }) {
  const { ref, width } = useMeasuredWidth<HTMLDivElement>();
  const size = Math.max(64, Math.min(120, width || 80));
  const pad = size * 0.15;
  const cx = size / 2;
  const cy = size / 2;
  const r = size * 0.375;
  const total = row.bull + row.bear + row.neutral || 1;
  const axes = [
    { label: '热度', value: Math.min(1, row.count / 20) },
    { label: '看多', value: row.bull / total },
    { label: '看空', value: row.bear / total },
    { label: '中性', value: row.neutral / total },
    { label: '强度', value: Math.min(1, Math.abs(row.score ?? 0) * 1.5) },
  ];
  const angleStep = (2 * Math.PI) / axes.length;
  const points = axes
    .map((a, i) => {
      const angle = -Math.PI / 2 + i * angleStep;
      const rr = r * a.value;
      return {
        x: cx + rr * Math.cos(angle),
        y: cy + rr * Math.sin(angle),
        lx: cx + (r + size * 0.12) * Math.cos(angle),
        ly: cy + (r + size * 0.12) * Math.sin(angle),
        label: a.label,
      };
    });
  const path = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`)
    .join(' ') + ' Z';
  return (
    <div ref={ref} className="ad-sentiment-radar">
      <svg width="100%" height="100%" viewBox={`-${pad} -${pad} ${size + pad * 2} ${size + pad * 2}`}>
        <circle cx={cx} cy={cy} r={r * 0.33} fill="none" stroke="var(--border-default)" strokeWidth={0.5} strokeOpacity={0.5} strokeDasharray="2 2" />
        <circle cx={cx} cy={cy} r={r * 0.66} fill="none" stroke="var(--border-default)" strokeWidth={0.5} strokeOpacity={0.5} strokeDasharray="2 2" />
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--border-default)" strokeWidth={0.5} />
        <path d={path} fill="var(--color-warning-hover-dim)" stroke="var(--color-warning-bright)" strokeWidth={1.25} />
        {points.map((p, i) => (
          <text
            key={i}
            x={p.lx}
            y={p.ly}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize={Math.max(15, size * 0.1875)}
            fill="var(--text-tertiary)"
          >
            {p.label}
          </text>
        ))}
      </svg>
    </div>
  );
}

/** Measure a container's width so Sparkline can render a full-width path. */
function useMeasuredWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setWidth(el.getBoundingClientRect().width);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    window.addEventListener('resize', update);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', update);
    };
  }, []);

  return { ref, width };
}

export default function SentimentOverview() {
  const navigate = useNavigate();
  const mode = useSettingsStore((s) => s.mode);
  const [market, setMarket] = useState<NewsMarket | 'all'>('all');
  const [importanceMin, setImportanceMin] = useState<number>(3);
  const [search, setSearch] = useState('');
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const { ref: sparklineRef, width: sparklineWidth } = useMeasuredWidth<HTMLDivElement>();

  // Pull a large enough sample so heatmap is meaningful.
  const { data, isLoading, isError } = useQuery({
    queryKey: ['sentiment-feed', market, importanceMin],
    queryFn: () =>
      newsApi
        .list({
          market: market === 'all' ? undefined : market,
          importance_min: importanceMin as ImportanceLevel,
          page: 1,
          page_size: PAGE_SIZE,
        })
        .then((r) => r.data.items),
    staleTime: 60_000,
  });

  const aggregates = useMemo(() => aggregateBySymbol(data ?? []), [data]);
  const filtered = useMemo(() => {
    const q = search.trim().toUpperCase();
    const list = q ? aggregates.filter((a) => a.symbol.toUpperCase().includes(q)) : aggregates;
    return list.sort((a, b) => b.count - a.count);
  }, [aggregates, search]);

  // Compute distribution for the selected symbol (used in detail strip).
  const selected = useMemo(
    () => (selectedSymbol ? aggregates.find((a) => a.symbol === selectedSymbol) ?? null : null),
    [selectedSymbol, aggregates]
  );

  // Top movers — biggest |score| across all symbols.
  const topMovers = useMemo(
    () =>
      [...aggregates]
        .filter((a) => a.score != null)
        .sort((a, b) => Math.abs(b.score!) - Math.abs(a.score!))
        .slice(0, 5),
    [aggregates]
  );

  // Persist last market filter so the page resumes where the user left off.
  useEffect(() => {
    try {
      const saved = localStorage.getItem('sentiment-market');
      if (saved && (MARKET_OPTIONS.find((o) => o.value === saved))) {
        setMarket(saved as NewsMarket | 'all');
      }
    } catch {
      // ignore
    }
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem('sentiment-market', market);
    } catch {
      // ignore
    }
  }, [market]);

  return (
    <AdxShell>
      <PageShell maxWidth="wide">
        <div className="sentiment-page">
        <PageHeader
          title="散户情绪看板"
          description="按市场聚合的新闻情绪分布 · 重要性与看多/看空比"
        />

        <FilterToolbar total={`${filtered.length} 个标的 · ${data?.length ?? 0} 条资讯`}>
          <div className="ad-scroll-hint">
            <Segmented
              value={market}
              onChange={(v) => setMarket(v as NewsMarket | 'all')}
              options={MARKET_OPTIONS}
            />
          </div>
          <span className="ad-filter-label">重要性 ≥</span>
          <Select
            value={importanceMin}
            onChange={setImportanceMin}
            options={[1, 2, 3, 4, 5].map((n) => ({ value: n, label: `${n} ★` }))}
            className="ad-select--xxs"
          />
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索标的代码…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="ad-input--md"
          />
        </FilterToolbar>

        {isError ? (
          <Alert
            type="error"
            message="加载情绪数据失败"
            showIcon
            className="ad-mb-5"
          />
        ) : null}

        <div className="ad-news-layout">
          {/* Heatmap */}
          <Panel
            variant="default"
            title={
              <span>
                <HeartOutlined className="ad-icon-title" />
                全市场情绪热力图
              </span>
            }
            padding="md"
          >
            {isLoading ? (
              <Skeleton active paragraph={{ rows: 8 }} />
            ) : filtered.length === 0 ? (
              <EmptyState title="暂无符合条件的数据" />
            ) : (
              <div className="ad-heatmap-grid">
                {filtered.map((row) => {
                  // Average importance of source articles for color intensity.
                  const avgImportance = (() => {
                    const items = (data ?? []).filter((a) =>
                      a.symbols.some((s) => s.symbol === row.symbol)
                    );
                    if (items.length === 0) return null;
                    const total = items.reduce((acc, a) => acc + (a.importance ?? 3), 0);
                    return Math.round(total / items.length) as ImportanceLevel;
                  })();
                  return (
                    <Tooltip
                      key={row.symbol}
                      title={
                        <div className="ad-tooltip-list">
                          <div>
                            <InstrumentCodeTag
                              code={row.symbol}
                              name={row.name ?? undefined}
                              name_zh={row.name_zh}
                            />
                            {row.market ? <span> · {row.market}</span> : null}
                          </div>
                          <div>情绪分数: {row.score != null ? row.score.toFixed(2) : '—'}</div>
                          <div>资讯数: {row.count}</div>
                          {row.label && <div>情绪标签: {SENTIMENT_LABELS[row.label]}</div>}
                        </div>
                      }
                    >
                      <div
                        role="button"
                        tabIndex={0}
                        aria-label={`选中 ${row.symbol}（资讯 ${row.count} 篇）`}
                        onClick={() => {
                          setSelectedSymbol(row.symbol);
                          message.info(`已选中: ${row.symbol}`);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            setSelectedSymbol(row.symbol);
                            message.info(`已选中: ${row.symbol}`);
                          }
                        }}
                        className={`ad-heatmap-cell ${selectedSymbol === row.symbol ? 'ad-heatmap-cell--active' : ''}`}
                        style={heatmapVars(row.score, avgImportance)}
                      >
                        <div className="ad-heatmap-cell__symbol">
                          <InstrumentCodeTag
                            code={row.symbol}
                            name={row.name ?? undefined}
                            name_zh={row.name_zh}
                          />
                        </div>
                        <div className="ad-heatmap-cell__row">
                          <span
                            className={`ad-heatmap-cell__score ${row.label ? `ad-heatmap-cell__score--${row.label}` : 'ad-heatmap-cell__score--neutral'}`}
                          >
                            {row.score != null ? row.score.toFixed(2) : '—'}
                          </span>
                          <span className="ad-heatmap-cell__count">
                            {row.count} 篇
                          </span>
                        </div>
                      </div>
                    </Tooltip>
                  );
                })}
              </div>
            )}
          </Panel>

          {/* Right column */}
          <div className="dashboard-side-stack">
            {/* Selected symbol detail */}
            <Panel
              variant="default"
              title={
                selectedSymbol
                  ? `单标详情 · ${selectedSymbol}`
                  : '单标详情'
              }
              padding="md"
            >
              {!selected ? (
                <EmptyState title="在左侧热力图选择一个标的" />
              ) : (
                <div>
                  <div className="ad-detail-score-header">
                    <span
                      className={`ad-detail-score-value ${selected.label ? `ad-detail-score-value--${selected.label}` : 'ad-detail-score-value--neutral'}`}
                    >
                      {selected.score != null ? selected.score.toFixed(2) : '—'}
                    </span>
                    <ThemeTag
                      variant={
                        selected.label === 'positive'
                          ? 'rise'
                          : selected.label === 'negative'
                            ? 'fall'
                            : 'neutral'
                      }
                    >
                      {selected.label ? SENTIMENT_LABELS[selected.label] : '无数据'}
                    </ThemeTag>
                  </div>

                  <div className="ad-text-small ad-text-tertiary ad-mb-2">
                    14 日情绪曲线
                  </div>
                  <div ref={sparklineRef} className="ad-sentiment-sparkline ad-mb-4">
                    <Sparkline
                      data={selected.sparkline}
                      width={Math.max(1, Math.floor(sparklineWidth))}
                      height={48}
                    />
                  </div>

                  <ResponsiveGrid cols={2} gap="sm" stretch>
                    <div className="ad-flex ad-items-center">
                      <PieBreakdown row={selected} />
                    </div>
                    <div>
                      <div className="ad-text-small ad-text-tertiary">
                        <HelpPopover termKey="bull_bear_ratio" mode={mode}>多空比</HelpPopover>
                      </div>
                      <div className="ad-text-primary ad-font-medium ad-mb-2">
                        {selected.bear > 0
                          ? (selected.bull / selected.bear).toFixed(2)
                          : '∞'}
                      </div>
                      <Button
                        size="small"
                        onClick={() =>
                          navigate(`/news?symbol=${encodeURIComponent(selected.symbol)}`)
                        }
                      >
                        查看资讯 →
                      </Button>
                    </div>
                  </ResponsiveGrid>

                  <div className="ad-mt-4">
                    <div className="ad-text-small ad-text-tertiary ad-mb-2">
                      观点分布
                    </div>
                    <DistributionRadar row={selected} />
                  </div>
                </div>
              )}
            </Panel>

            {/* Top movers */}
            <Panel
              variant="default"
              title={
                <span>
                  <FireOutlined className="ad-icon-title" />
                  情绪最强烈
                </span>
              }
              padding="md"
            >
              {isLoading ? (
                <Skeleton active paragraph={{ rows: 4 }} />
              ) : topMovers.length === 0 ? (
                <EmptyState title="暂无数据" />
              ) : (
                <Space direction="vertical" size={6} className="ad-w-full">
                  {topMovers.map((row) => (
                    <div
                      key={row.symbol}
                      role="button"
                      tabIndex={0}
                      aria-label={`选中 ${row.symbol} (情绪分数 ${row.score?.toFixed(2) ?? '—'})`}
                      onClick={() => setSelectedSymbol(row.symbol)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          setSelectedSymbol(row.symbol);
                        }
                      }}
                      className="ad-mover-row"
                    >
                      {(row.score ?? 0) >= 0 ? (
                        <ArrowUpOutlined className="ad-mover-arrow--up" />
                      ) : (
                        <ArrowDownOutlined className="ad-mover-arrow--down" />
                      )}
                      <span className="ad-mover-name">
                        <InstrumentCodeTag
                          code={row.symbol}
                          name={row.name ?? undefined}
                          name_zh={row.name_zh}
                        />
                      </span>
                      <span
                        className={`ad-mover-score ${row.label ? `ad-mover-score--${row.label}` : 'ad-mover-score--neutral'}`}
                      >
                        {row.score != null ? row.score.toFixed(2) : '—'}
                      </span>
                    </div>
                  ))}
                </Space>
              )}
            </Panel>
          </div>
        </div>
        </div>
      </PageShell>
    </AdxShell>
  );
}
