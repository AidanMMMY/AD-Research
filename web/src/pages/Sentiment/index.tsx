import { useState, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Input,
  Segmented,
  Empty,
  Skeleton,
  Tag,
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
import Panel from '@/components/Panel';
import Sparkline from '@/components/Sparkline';

const MARKET_OPTIONS: { label: string; value: NewsMarket | 'all' }[] = [
  { label: '全部', value: 'all' },
  { label: 'A 股', value: 'cn_a' },
  { label: '美股', value: 'us' },
  { label: '加密', value: 'crypto' },
];

const SENTIMENT_COLORS: Record<SentimentLabel, string> = {
  positive: '#52c41a',
  neutral: '#8c8c8c',
  negative: '#f5222d',
};

const SENTIMENT_LABELS: Record<SentimentLabel, string> = {
  positive: '看多',
  neutral: '中性',
  negative: '看空',
};

interface SymbolAggregate {
  symbol: string;
  market: string;
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
}

const PAGE_SIZE = 100;

/**
 * Group articles by symbol, compute importance-weighted aggregate
 * sentiment, and produce per-day sparkline points.
 */
function aggregateBySymbol(articles: NewsArticle[]): SymbolAggregate[] {
  type Bucket = {
    symbol: string;
    market: string;
    articles: NewsArticle[];
    scoreSum: number;
    weightSum: number;
    bull: number;
    bear: number;
    neutral: number;
  };

  const buckets = new Map<string, Bucket>();
  for (const a of articles) {
    for (const s of a.symbols) {
      const cur = buckets.get(s.symbol) ?? {
        symbol: s.symbol,
        market: s.market,
        articles: [],
        scoreSum: 0,
        weightSum: 0,
        bull: 0,
        bear: 0,
        neutral: 0,
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

/** Color hue for a heatmap cell, blending sentiment + importance. */
function heatmapColor(score: number | null, importance: ImportanceLevel | null): string {
  if (score == null) return 'var(--bg-elevated)';
  const intensity = Math.min(1, Math.abs(score) * 1.4);
  const alpha = 0.15 + 0.55 * intensity * (importance != null ? importance / 5 : 0.5);
  const r = score > 0 ? 82 : score < 0 ? 245 : 140;
  const g = score > 0 ? 196 : score < 0 ? 34 : 140;
  const b = score > 0 ? 26 : score < 0 ? 45 : 140;
  return `rgba(${r}, ${g}, ${b}, ${alpha.toFixed(2)})`;
}

/** Compute pie-slice percentage paths for bull/bear/neutral breakdown. */
function PieBreakdown({ row }: { row: SymbolAggregate }) {
  const total = row.bull + row.bear + row.neutral;
  if (total === 0) {
    return <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>—</div>;
  }
  const slices = [
    { label: '多', value: row.bull, color: SENTIMENT_COLORS.positive },
    { label: '空', value: row.bear, color: SENTIMENT_COLORS.negative },
    { label: '中', value: row.neutral, color: SENTIMENT_COLORS.neutral },
  ];
  const size = 56;
  const r = 22;
  const cx = size / 2;
  const cy = size / 2;
  let acc = 0;
  return (
    <Tooltip
      title={
        <div style={{ fontSize: 12 }}>
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
          fontSize={8}
          fill="var(--text-tertiary)"
        >
          {p.label}
        </text>
      ))}
    </svg>
  );
}

export default function SentimentOverview() {
  const navigate = useNavigate();
  const [market, setMarket] = useState<NewsMarket | 'all'>('all');
  const [importanceMin, setImportanceMin] = useState<number>(3);
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
        散户情绪看板
      </h1>
      <p
        style={{
          margin: '0 0 24px',
          color: 'var(--text-tertiary)',
          fontSize: 'var(--text-body-size)',
        }}
      >
        按市场聚合的新闻情绪分布 · 重要性与看多/看空比
      </p>

      {/* Filter bar */}
      <div
        style={{
          background: 'var(--card-bg)',
          border: '1px solid var(--card-border)',
          borderRadius: 'var(--card-radius)',
          padding: '16px 20px',
          marginBottom: 20,
          display: 'flex',
          gap: 12,
          flexWrap: 'wrap',
          alignItems: 'center',
        }}
      >
        <Segmented
          value={market}
          onChange={(v) => setMarket(v as NewsMarket | 'all')}
          options={MARKET_OPTIONS}
        />
        <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>重要性 ≥</span>
        <Select
          value={importanceMin}
          onChange={setImportanceMin}
          options={[1, 2, 3, 4, 5].map((n) => ({ value: n, label: `${n} ★` }))}
          style={{ width: 90 }}
        />
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="搜索标的代码…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 220 }}
        />
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
          {filtered.length} 个标的 · {data?.length ?? 0} 条资讯
        </span>
      </div>

      {isError ? (
        <Alert
          type="error"
          message="加载情绪数据失败"
          showIcon
          style={{ marginBottom: 20 }}
        />
      ) : null}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 2.2fr) minmax(0, 1fr)',
          gap: 20,
        }}
      >
        {/* Heatmap */}
        <Panel
          variant="minimal"
          title={
            <span>
              <HeartOutlined style={{ marginRight: 6, color: 'var(--accent)' }} />
              全市场情绪热力图
            </span>
          }
          padding="md"
        >
          {isLoading ? (
            <Skeleton active paragraph={{ rows: 8 }} />
          ) : filtered.length === 0 ? (
            <Empty description="暂无符合条件的数据" />
          ) : (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))',
                gap: 8,
              }}
            >
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
                      <div style={{ fontSize: 12 }}>
                        <div>
                          <strong>{row.symbol}</strong> · {row.market}
                        </div>
                        <div>情绪分数: {row.score != null ? row.score.toFixed(2) : '—'}</div>
                        <div>资讯数: {row.count}</div>
                        {row.label && <div>情绪标签: {SENTIMENT_LABELS[row.label]}</div>}
                      </div>
                    }
                  >
                    <div
                      onClick={() => {
                        setSelectedSymbol(row.symbol);
                        message.info(`已选中: ${row.symbol}`);
                      }}
                      style={{
                        background: heatmapColor(row.score, avgImportance),
                        border:
                          selectedSymbol === row.symbol
                            ? '1px solid var(--accent)'
                            : '1px solid var(--border-default)',
                        borderRadius: 'var(--radius-md)',
                        padding: '10px 12px',
                        cursor: 'pointer',
                        transition: 'transform var(--transition-fast)',
                        minHeight: 64,
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.transform = 'translateY(-1px)';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.transform = 'translateY(0)';
                      }}
                    >
                      <div
                        style={{
                          fontSize: 13,
                          fontWeight: 600,
                          color: 'var(--text-primary)',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {row.symbol}
                      </div>
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          marginTop: 4,
                        }}
                      >
                        <span
                          style={{
                            fontSize: 11,
                            color: row.label ? SENTIMENT_COLORS[row.label] : 'var(--text-tertiary)',
                            fontWeight: 500,
                          }}
                        >
                          {row.score != null ? row.score.toFixed(2) : '—'}
                        </span>
                        <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Selected symbol detail */}
          <Panel
            variant="minimal"
            title={
              selectedSymbol
                ? `单标详情 · ${selectedSymbol}`
                : '单标详情'
            }
            padding="md"
          >
            {!selected ? (
              <Empty
                description="在左侧热力图选择一个标的"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                style={{ padding: '20px 0' }}
              />
            ) : (
              <div>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'baseline',
                    justifyContent: 'space-between',
                    marginBottom: 12,
                  }}
                >
                  <span
                    style={{
                      fontSize: 28,
                      fontWeight: 700,
                      color:
                        selected.label
                          ? SENTIMENT_COLORS[selected.label]
                          : 'var(--text-primary)',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    {selected.score != null ? selected.score.toFixed(2) : '—'}
                  </span>
                  <Tag
                    color={
                      selected.label === 'positive'
                        ? 'green'
                        : selected.label === 'negative'
                          ? 'red'
                          : 'default'
                    }
                  >
                    {selected.label ? SENTIMENT_LABELS[selected.label] : '无数据'}
                  </Tag>
                </div>

                <div
                  style={{
                    fontSize: 12,
                    color: 'var(--text-tertiary)',
                    marginBottom: 4,
                  }}
                >
                  14 日情绪曲线
                </div>
                <div style={{ marginBottom: 16 }}>
                  <Sparkline
                    data={selected.sparkline}
                    width={240}
                    height={48}
                    chinaConvention={false}
                  />
                </div>

                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'auto 1fr',
                    gap: 12,
                    alignItems: 'center',
                  }}
                >
                  <PieBreakdown row={selected} />
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                      多空比
                    </div>
                    <div
                      style={{
                        fontSize: 14,
                        color: 'var(--text-primary)',
                        fontWeight: 500,
                        marginBottom: 6,
                      }}
                    >
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
                </div>

                <div style={{ marginTop: 16 }}>
                  <div
                    style={{
                      fontSize: 12,
                      color: 'var(--text-tertiary)',
                      marginBottom: 6,
                    }}
                  >
                    观点分布
                  </div>
                  <DistributionRadar row={selected} />
                </div>
              </div>
            )}
          </Panel>

          {/* Top movers */}
          <Panel
            variant="minimal"
            title={
              <span>
                <FireOutlined style={{ marginRight: 6, color: 'var(--accent)' }} />
                情绪最强烈
              </span>
            }
            padding="md"
          >
            {isLoading ? (
              <Skeleton active paragraph={{ rows: 4 }} />
            ) : topMovers.length === 0 ? (
              <Empty
                description="暂无数据"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            ) : (
              <Space direction="vertical" size={6} style={{ width: '100%' }}>
                {topMovers.map((row) => (
                  <div
                    key={row.symbol}
                    onClick={() => setSelectedSymbol(row.symbol)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '6px 0',
                      cursor: 'pointer',
                      borderBottom: '1px solid var(--border-default)',
                    }}
                  >
                    {(row.score ?? 0) >= 0 ? (
                      <ArrowUpOutlined style={{ color: SENTIMENT_COLORS.positive, fontSize: 12 }} />
                    ) : (
                      <ArrowDownOutlined style={{ color: SENTIMENT_COLORS.negative, fontSize: 12 }} />
                    )}
                    <span style={{ fontSize: 13, color: 'var(--text-primary)', flex: 1 }}>
                      {row.symbol}
                    </span>
                    <span
                      style={{
                        fontSize: 13,
                        fontFamily: 'var(--font-mono)',
                        color: row.label ? SENTIMENT_COLORS[row.label] : 'var(--text-tertiary)',
                        fontWeight: 500,
                      }}
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
  );
}
