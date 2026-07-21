import { useState, useMemo, useEffect, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Input,
  Segmented,
  Tooltip,
  Select,
  message,
  Space,
  Alert,
  Button,
  Table,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  SearchOutlined,
  HeartOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  FireOutlined,
  BarChartOutlined,
} from '@ant-design/icons';
import { newsApi } from '@/api/news';
import { researchApi } from '@/api/research';
import type {
  NewsArticle,
  NewsMarket,
  SentimentLabel,
  ImportanceLevel,
  SentimentAggregateItem,
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
import LoadingBlock from '@/components/LoadingBlock';
import ThemeTag, { type ThemeTagVariant } from '@/components/ThemeTag';
import { useSettingsStore, type ColorConvention } from '@/stores/settings';

const MARKET_OPTIONS: { label: string; value: NewsMarket | 'all' }[] = [
  { label: '全部', value: 'all' },
  { label: 'A 股', value: 'cn_a' },
  { label: '美股', value: 'us' },
  { label: '加密', value: 'crypto' },
];

const DAYS_OPTIONS: { label: string; value: number }[] = [
  { label: '7 天', value: 7 },
  { label: '14 天', value: 14 },
  { label: '30 天', value: 30 },
];

type ViewMode = 'news' | 'aggregate';

const VIEW_OPTIONS: { label: string; value: ViewMode; icon: ReactNode }[] = [
  { label: '资讯情绪', value: 'news', icon: <HeartOutlined /> },
  { label: '按标的聚合', value: 'aggregate', icon: <BarChartOutlined /> },
];

const POLL_SLICE_COLORS: Record<SentimentLabel, string> = {
  positive: 'var(--color-rise)',
  neutral: 'var(--text-tertiary)',
  negative: 'var(--color-fall)',
};

/** Legend rows for the heatmap score scale; thresholds mirror aggregateBySymbol. */
const SENTIMENT_LEGEND: { label: SentimentLabel; example: string }[] = [
  { label: 'positive', example: '分数 > +0.2，如 +0.45' },
  { label: 'neutral', example: '介于 ±0.2 之间' },
  { label: 'negative', example: '分数 < -0.2，如 -0.60' },
];

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

/** Color hue for a heatmap cell, blending sentiment + importance.
 *  Honors the user's `colorConvention` setting (china = red up/green down,
 *  us = green up/red down) so the heatmap direction flips together with
 *  the rest of the app when the user toggles the convention. */
function heatmapColor(
  score: number | null,
  importance: ImportanceLevel | null,
  convention: ColorConvention = 'china',
): string {
  if (score == null) return 'var(--bg-elevated)';
  const intensity = Math.min(1, Math.abs(score) * 1.4);
  const alpha = 0.15 + 0.55 * intensity * (importance != null ? importance / 5 : 0.5);
  const isPositive = score > 0;
  const isNegative = score < 0;
  // china convention: rise=red(245,34,45), fall=green(82,196,26)
  // us convention:    rise=green(82,196,26), fall=red(245,34,45)
  let r: number, g: number, b: number;
  if (convention === 'us') {
    r = isPositive ? 82 : isNegative ? 245 : 140;
    g = isPositive ? 196 : isNegative ? 34 : 140;
    b = isPositive ? 26 : isNegative ? 45 : 140;
  } else {
    r = isPositive ? 245 : isNegative ? 82 : 140;
    g = isPositive ? 34 : isNegative ? 196 : 140;
    b = isPositive ? 45 : isNegative ? 26 : 140;
  }
  return `rgba(${r}, ${g}, ${b}, ${alpha.toFixed(2)})`;
}

/** Compute pie-slice percentage paths for bull/bear/neutral breakdown. */
function PieBreakdown({ row }: { row: SymbolAggregate }) {
  const total = row.bull + row.bear + row.neutral;
  if (total === 0) {
    return <span className="ad-text-small ad-text-tertiary">—</span>;
  }
  const slices = [
    { label: '多', value: row.bull, color: POLL_SLICE_COLORS.positive },
    { label: '空', value: row.bear, color: POLL_SLICE_COLORS.negative },
    { label: '中', value: row.neutral, color: POLL_SLICE_COLORS.neutral },
  ];
  const size = 56;
  const r = 22;
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
      <svg width={size} height={size}>
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
    </Tooltip>
  );
}

/** 5-axis radar: importance, count, bull ratio, score abs, freshness. */
function DistributionRadar({ row }: { row: SymbolAggregate }) {
  const size = 80;
  const cx = size / 2;
  const cy = size / 2;
  const r = 30;
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
        lx: cx + (r + 9) * Math.cos(angle),
        ly: cy + (r + 9) * Math.sin(angle),
        label: a.label,
      };
    });
  const path = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`)
    .join(' ') + ' Z';
  return (
    <svg width={size} height={size}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--border-default)" strokeWidth={0.5} />
      <path d={path} fill="var(--color-warning-bright-dim)" stroke="var(--color-warning-bright)" strokeWidth={1.25} />
      {points.map((p, i) => (
        <text
          key={i}
          x={p.lx}
          y={p.ly}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={10}
          fill="var(--text-tertiary)"
        >
          {p.label}
        </text>
      ))}
    </svg>
  );
}

/** Convert backend sentiment label into a ThemeTag variant. */
function labelToVariant(label: SentimentLabel | null | undefined): ThemeTagVariant {
  if (label === 'positive') return 'rise';
  if (label === 'negative') return 'fall';
  return 'neutral';
}

/** Mini pie for bull/bear/neutral on a SentimentAggregateItem row. */
function AggPieBreakdown({ row }: { row: SentimentAggregateItem }) {
  const total = row.bull + row.bear + row.neutral;
  if (total === 0) {
    return <span className="ad-text-small ad-text-tertiary">—</span>;
  }
  const slices = [
    { label: '多', value: row.bull, color: POLL_SLICE_COLORS.positive },
    { label: '空', value: row.bear, color: POLL_SLICE_COLORS.negative },
    { label: '中', value: row.neutral, color: POLL_SLICE_COLORS.neutral },
  ];
  const size = 56;
  const r = 22;
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
      <svg width={size} height={size}>
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
    </Tooltip>
  );
}

interface SentimentAggregateTableProps {
  data: SentimentAggregateItem[];
  loading: boolean;
  market: NewsMarket | 'all';
  days: number;
  onSymbolClick: (symbol: string) => void;
}

function SentimentAggregateTable({
  data,
  loading,
  market,
  days,
  onSymbolClick,
}: SentimentAggregateTableProps) {
  const navigate = useNavigate();
  const columns: ColumnsType<SentimentAggregateItem> = [
    {
      title: '标的',
      dataIndex: 'symbol',
      key: 'symbol',
      fixed: 'left',
      render: (_, row) => (
        <div className="ad-sentiment-symbol-cell">
          <InstrumentCodeTag
            code={row.symbol}
            name={row.name ?? undefined}
            name_zh={row.name_zh}
          />
          <Button
            type="link"
            size="small"
            className="ad-sentiment-symbol-link"
            onClick={() => onSymbolClick(row.symbol)}
          >
            详情
          </Button>
        </div>
      ),
    },
    {
      title: '情绪标签',
      dataIndex: 'label',
      key: 'label',
      align: 'center',
      render: (label: SentimentLabel) => (
        <ThemeTag variant={labelToVariant(label)}>
          {SENTIMENT_LABELS[label] ?? label}
        </ThemeTag>
      ),
    },
    {
      title: '平均分',
      dataIndex: 'avg_score',
      key: 'avg_score',
      align: 'right',
      render: (v: number) => v.toFixed(2),
      sorter: (a, b) => a.avg_score - b.avg_score,
    },
    {
      title: '文章数',
      dataIndex: 'count',
      key: 'count',
      align: 'right',
      sorter: (a, b) => a.count - b.count,
    },
    {
      title: '多空比',
      key: 'breakdown',
      align: 'center',
      render: (_, row) => (
        <div className="ad-sentiment-breakdown">
          <AggPieBreakdown row={row} />
          <span className="ad-sentiment-breakdown-text">
            多 {Math.round(row.bull)} / 空 {Math.round(row.bear)} / 中 {Math.round(row.neutral)}
          </span>
        </div>
      ),
    },
    {
      title: '14日趋势',
      key: 'sparkline',
      className: 'ad-sentiment-sparkline-col',
      render: (_, row) => (
        <Sparkline
          data={row.sparkline}
          width={120}
          height={36}
          style={{ width: '100%', minWidth: 80 }}
        />
      ),
    },
    {
      title: '最新资讯',
      key: 'latest',
      className: 'ad-sentiment-latest-col',
      render: (_, row) => {
        if (!row.latest_title) return <span className="ad-text-tertiary">—</span>;
        const canNavigate = row.latest_id || row.latest_url;
        return (
          <Tooltip title={row.latest_title}>
            {canNavigate ? (
              <Button
                type="link"
                size="small"
                className="ad-sentiment-latest-title"
                onClick={() => {
                  if (row.latest_id) {
                    navigate(`/news/${row.latest_id}`);
                  } else if (row.latest_url) {
                    window.open(row.latest_url, '_blank', 'noopener,noreferrer');
                  }
                }}
              >
                {row.latest_title}
              </Button>
            ) : (
              <span className="ad-sentiment-latest-title ad-text-primary">
                {row.latest_title}
              </span>
            )}
          </Tooltip>
        );
      },
    },
  ];

  return (
    <Panel
      variant="default"
      title={
        <span>
          <BarChartOutlined className="phase5c-icon-title" />
          按标的情绪汇总
        </span>
      }
      padding="md"
    >
      {loading ? (
        <LoadingBlock size="lg" />
      ) : data.length === 0 ? (
        <EmptyState
          title="暂无情绪汇总数据"
          description={`${market === 'all' ? '全部市场' : MARKET_OPTIONS.find((o) => o.value === market)?.label} · 近 ${days} 天`}
        />
      ) : (
        <Table
          dataSource={data}
          columns={columns}
          rowKey="symbol"
          pagination={{ pageSize: 50, hideOnSinglePage: true }}
          scroll={{ x: 720 }}
          className="ad-sentiment-aggregate-table"
        />
      )}
    </Panel>
  );
}

export default function SentimentOverview() {
  const navigate = useNavigate();
  const mode = useSettingsStore((s) => s.mode);
  const colorConvention = useSettingsStore((s) => s.colorConvention);
  const [view, setView] = useState<ViewMode>('news');
  const [days, setDays] = useState<number>(14);
  // Restore the last market filter via lazy init so the page resumes
  // where the user left off (keeps setState out of effects).
  const [market, setMarket] = useState<NewsMarket | 'all'>(() => {
    try {
      const saved = localStorage.getItem('sentiment-market');
      if (saved && MARKET_OPTIONS.find((o) => o.value === saved)) {
        return saved as NewsMarket | 'all';
      }
    } catch {
      // ignore
    }
    return 'all';
  });
  const [importanceMin, setImportanceMin] = useState<number>(1);
  const [search, setSearch] = useState('');
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);

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
    enabled: view === 'news',
  });

  const {
    data: aggData,
    isLoading: aggLoading,
    isError: aggError,
  } = useQuery({
    queryKey: ['sentiment-aggregate', market, days],
    queryFn: () =>
      researchApi
        .sentimentAggregate({
          market: market === 'all' ? undefined : market,
          days,
        })
        .then((r) => r.data),
    staleTime: 60_000,
    refetchInterval: 60_000,
    enabled: view === 'aggregate',
  });

  const aggregates = useMemo(() => aggregateBySymbol(data ?? []), [data]);
  const filtered = useMemo(() => {
    const q = search.trim().toUpperCase();
    const list = q ? aggregates.filter((a) => a.symbol.toUpperCase().includes(q)) : aggregates;
    return list.sort((a, b) => b.count - a.count);
  }, [aggregates, search]);

  const filteredAgg = useMemo(() => {
    const q = search.trim().toUpperCase();
    const list = aggData ?? [];
    if (!q) return list;
    return list.filter(
      (a) =>
        a.symbol.toUpperCase().includes(q) ||
        (a.name ?? '').toUpperCase().includes(q) ||
        (a.name_zh ?? '').toUpperCase().includes(q)
    );
  }, [aggData, search]);

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
      localStorage.setItem('sentiment-market', market);
    } catch {
      // ignore
    }
  }, [market]);

  return (
    <PageShell maxWidth="wide" className="sentiment-page">
      <PageHeader
        title="散户情绪看板"
        description="按市场聚合的新闻情绪分布 · 重要性与看多/看空比"
      />

      <FilterToolbar>
        <Segmented
          size="large"
          value={view}
          onChange={(v) => setView(v as ViewMode)}
          options={VIEW_OPTIONS.map((o) => ({
            value: o.value,
            label: (
              <span className="ad-segmented-with-icon">
                {o.icon}
                {o.label}
              </span>
            ),
          }))}
        />
        <Segmented
          size="large"
          value={market}
          onChange={(v) => setMarket(v as NewsMarket | 'all')}
          options={MARKET_OPTIONS}
        />
        {view === 'news' ? (
          <>
            <span className="ad-filter-label">重要性 ≥</span>
            <Select
              value={importanceMin}
              onChange={setImportanceMin}
              options={[1, 2, 3, 4, 5].map((n) => ({ value: n, label: `${n} ★` }))}
              className="phase5c-select--xxs"
            />
          </>
        ) : (
          <>
            <span className="ad-filter-label">窗口</span>
            <Select
              value={days}
              onChange={setDays}
              options={DAYS_OPTIONS}
              className="phase5c-select--xxs"
            />
          </>
        )}
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder={view === 'news' ? '搜索标的代码…' : '搜索标的代码或名称…'}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="phase5c-input--md"
        />
        {/* Result count sits inline, right after the filter controls. */}
        <span className="filter-toolbar__total">
          {view === 'news'
            ? `${filtered.length} 个标的 · ${data?.length ?? 0} 条资讯`
            : `${filteredAgg.length} 个标的 · ${aggData?.length ?? 0} 条汇总`}
        </span>
      </FilterToolbar>

      {isError || aggError ? (
        <Alert
          type="error"
          message="加载情绪数据失败"
          showIcon
          className="ad-mb-5"
        />
      ) : null}

      {view === 'news' ? (
        <div className="ad-news-layout">
        {/* Heatmap */}
        <Panel
          variant="default"
          title={
            <span>
              <HeartOutlined className="phase5c-icon-title" />
              全市场情绪热力图
            </span>
          }
          padding="md"
        >
          {isLoading ? (
            <LoadingBlock size="lg" />
          ) : filtered.length === 0 ? (
            <EmptyState
              title="暂无符合条件的数据"
              description="当前筛选条件下没有结果，可以放宽条件试试"
              action={
                <Button
                  onClick={() => {
                    setImportanceMin(1);
                    setSearch('');
                  }}
                >
                  放宽筛选
                </Button>
              }
            />
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
                      style={{ background: heatmapColor(row.score, avgImportance, colorConvention) }}
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

        {/* Right column — legend + detail + top movers in a single card. */}
        <div className="dashboard-side-stack">
          <Panel
            variant="default"
            title={
              selectedSymbol
                ? `单标详情 · ${selectedSymbol}`
                : '单标详情'
            }
            padding="md"
          >
            {/* Legend: mini colour dot + worked example so heatmap
                scores read at a glance. */}
            <div className="ad-sentiment-legend">
              {SENTIMENT_LEGEND.map((row) => (
                <div key={row.label} className="ad-sentiment-legend__row">
                  <span
                    className={`ad-sentiment-legend__dot ad-sentiment-legend__dot--${row.label}`}
                  />
                  <span className="ad-sentiment-legend__label">
                    {SENTIMENT_LABELS[row.label]}
                  </span>
                  <span className="ad-sentiment-legend__example">
                    {row.example}
                  </span>
                </div>
              ))}
            </div>

            {!selected ? (
              <EmptyState
                className="empty-state--in-card"
                title="在左侧热力图选择一个标的"
              />
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
                <div className="ad-mb-4 ad-w-full" style={{ width: '100%' }}>
                  <Sparkline
                    data={selected.sparkline}
                    width={240}
                    height={48}
                    style={{ width: '100%' }}
                  />
                </div>

                <ResponsiveGrid cols={2} gap="sm">
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
            {/* Top movers */}
            <div className="ad-sentiment-movers">
              <div className="ad-sentiment-movers__title">
                <FireOutlined className="phase5c-icon-title" />
                情绪最强烈
              </div>
              {isLoading ? (
                <LoadingBlock size="md" />
              ) : topMovers.length === 0 ? (
                <EmptyState className="empty-state--in-card" title="暂无数据" />
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
            </div>
          </Panel>
        </div>
      </div>
      ) : (
        <SentimentAggregateTable
          data={filteredAgg}
          loading={aggLoading}
          market={market}
          days={days}
          onSymbolClick={(symbol) => navigate(`/instruments/${encodeURIComponent(symbol)}`)}
        />
      )}
    </PageShell>
  );
}
