/**
 * Global Markets page — covers overseas indices, US Treasury yields,
 * USD index, COMEX commodities and VIX.  Backed by FRED via the existing
 * `/macro/latest` and `/macro/indicators/{code}` endpoints.  See
 * docs/dev-notes/20260704-global-markets-roadmap.md.
 */

import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Skeleton, Table, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import SectionHeading from '@/components/SectionHeading';
import EmptyState from '@/components/EmptyState';
import Sparkline from '@/components/Sparkline';
import ReturnTag from '@/components/ReturnTag';
import LastUpdated from '@/components/LastUpdated';
import HelpTrigger from '@/components/HelpTrigger';
import { newsApi } from '@/api/news';
import type { NewsArticle } from '@/types/news';
import { useAIHelp } from '@/hooks/useAIHelp';
import {
  buildGlobalMarketsContext,
  type NewsArticleSummary,
} from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';
import {
  useMacroLatest,
  macroApi,
  type MacroIndicatorSeries,
  type MacroLatestItem,
} from '@/api/macro';

const { Text } = Typography;

/** Internal logical category key -> friendly Chinese display label. */
const CATEGORY_LABELS: Record<string, string> = {
  rate: '美债利率',
  fx: '外汇',
  commodity: '大宗商品',
  index: '主要指数',
  vol: '情绪 / 波动',
};
const CATEGORY_ORDER = ['rate', 'fx', 'commodity', 'index', 'vol'];

/** Codes we want to surface on the Global Markets page (in display order). */
const PRIMARY_CODES: string[] = [
  // ── Rates (UST curve) ──
  'us_dgs30',
  'us_dgs10',
  'us_dgs2',
  'us_t10y2y',
  // ── FX ──
  'global_dxy',
  'global_usdjpy',
  // ── Commodities ──
  'global_brent',
  'global_wti',
  'global_gold',
  // ── Cross-border Index ──
  'global_sp500',
  // ── Volatility (CBOE) ──
  'us_vix',
];

interface RowVm {
  code: string;
  name: string;
  region: string;
  unit: string;
  latest: number | null;
  previous: number | null;
  changePct: number | null;
  asOf: string | null;
  sparkline: number[];
}

function formatValue(value: number | null, unit: string): string {
  if (value == null || Number.isNaN(value)) return '—';
  if (unit === '%') return `${value.toFixed(2)}%`;
  if (Math.abs(value) >= 1000)
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return value.toFixed(2);
}

/**
 * Map a code to its logical category bucket.  Adding a new series
 * only needs an entry here.
 */
function inferCategoryKey(code: string): string {
  if (code.startsWith('us_dgs') || code.startsWith('us_t10y')) return 'rate';
  if (code === 'us_vix') return 'vol';
  if (code.startsWith('global_dxy') || code.startsWith('global_usdjpy')) return 'fx';
  if (
    code.startsWith('global_brent') ||
    code.startsWith('global_wti') ||
    code.startsWith('global_gold')
  )
    return 'commodity';
  if (code.startsWith('global_sp500')) return 'index';
  return 'index';
}

function CategoryBlock({ title, rows }: { title: string; rows: RowVm[] }): JSX.Element | null {
  if (rows.length === 0) return null;
  const columns: ColumnsType<RowVm> = [
    {
      title: '指标',
      dataIndex: 'name',
      key: 'name',
      width: 220,
      render: (n: string, row) => (
        <div>
          <Text strong>{n}</Text>
          <div>
            <Text type="secondary" className="ad-text-xs">
              {row.code} · {row.unit || '—'}
            </Text>
          </div>
        </div>
      ),
    },
    {
      title: '最新值',
      dataIndex: 'latest',
      key: 'latest',
      width: 140,
      align: 'right',
      render: (v: number | null, row) => (
        <Text strong className="tabular-nums">
          {formatValue(v, row.unit)}
        </Text>
      ),
    },
    {
      title: '日涨跌',
      dataIndex: 'changePct',
      key: 'changePct',
      width: 110,
      align: 'right',
      render: (v: number | null) =>
        v == null ? <Text type="secondary">—</Text> : <ReturnTag value={v} />,
    },
    {
      title: '近30日',
      dataIndex: 'sparkline',
      key: 'sparkline',
      width: 160,
      render: (s: number[]) =>
        s.length >= 2 ? (
          <Sparkline data={s} width={140} height={26} />
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: '数据日期',
      dataIndex: 'asOf',
      key: 'asOf',
      width: 130,
      render: (p: string | null) =>
        p ? <Text type="secondary">{p}</Text> : <Text type="secondary">未采集</Text>,
    },
    {
      title: '区域',
      dataIndex: 'region',
      key: 'region',
      width: 90,
      render: (r: string) =>
        r === 'global' ? <Tag color="geekblue">全球</Tag> : <Tag color="blue">美国</Tag>,
    },
  ];
  return (
    <section className="phase5c-section">
      <SectionHeading title={title} />
      <Panel>
        <div className="ad-density-dense ad-table-scroll">
          <Table<RowVm>
            rowKey="code"
            size="small"
            dataSource={rows}
            columns={columns}
            pagination={false}
            showHeader
            scroll={{ x: 'max-content' }}
          />
        </div>
      </Panel>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Recent-24h political / macro event stream (K12, 2026-07-04).
//
// Reuses the new ``event_category`` filter from the News API to surface
// geopolitics / central_bank / election / trade_war / sanction items in
// the last 24 hours at importance >= 4. Each row links into the News
// detail page. Stays self-contained so K11 can drop the rest of the
// page without losing the widget.
// ---------------------------------------------------------------------------

const POLITICAL_CATEGORIES = [
  'geopolitics',
  'central_bank',
  'election',
  'trade_war',
  'sanction',
];

const POLITICAL_CATEGORY_LABEL: Record<string, string> = {
  geopolitics: '地缘',
  central_bank: '央行',
  election: '选举',
  trade_war: '贸易战',
  sanction: '制裁',
};

const POLITICAL_CATEGORY_COLOR: Record<string, string> = {
  geopolitics: 'volcano',
  central_bank: 'geekblue',
  election: 'purple',
  trade_war: 'red',
  sanction: 'magenta',
};

/**
 * Shared hook: load the most recent political / macro news items
 * (geopolitics / central_bank / election / trade_war / sanction) in
 * the last 24 h with importance >= 4.  Lives at module scope so both
 * the on-page widget and the AI Help button consume the same cache
 * entry (and we only hit /news once per minute).
 */
function useRecentPoliticalEvents() {
  const since = useMemo(
    () => new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
    [],
  );
  return useQuery({
    queryKey: ['global-markets-recent-political', since],
    queryFn: () =>
      newsApi
        .list({
          event_category: POLITICAL_CATEGORIES,
          importance_min: 4,
          from_date: since,
          page: 1,
          page_size: 8,
        })
        .then((r) => r.data),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}

/**
 * Compact "recent 24h political events" panel. Renders nothing while
 * loading (so the rest of the page is not blocked), then either a
 * 5-row clickable list or an empty-state message.  The query lives in
 * ``useRecentPoliticalEvents`` so the AI Help button can reuse the
 * same cache entry.
 */
function Recent24hEvents(): JSX.Element | null {
  const navigate = useNavigate();
  const { data, isLoading, isError } = useRecentPoliticalEvents();

  if (isLoading) {
    return (
      <Panel title="最近 24h 重大政治 / 地缘事件" padding="md">
        <Skeleton active paragraph={{ rows: 3 }} />
      </Panel>
    );
  }
  if (isError) {
    return (
      <Panel title="最近 24h 重大政治 / 地缘事件" padding="md">
        <EmptyState title="事件流加载失败" />
      </Panel>
    );
  }
  const items: NewsArticle[] = data?.items ?? [];
  if (items.length === 0) {
    return (
      <Panel title="最近 24h 重大政治 / 地缘事件" padding="md">
        <EmptyState
          title="暂无 24h 内重大政治事件"
          description="一旦 LLM 抽取到 importance>=4 的地缘 / 央行 / 选举 / 贸易战 / 制裁事件，会在这里显示。"
        />
      </Panel>
    );
  }

  return (
    <Panel title="最近 24h 重大政治 / 地缘事件" padding="md">
      <ul className="ad-news-events-list">
        {items.map((a) => (
          <li
            key={a.id}
            className="ad-news-events-list__item"
            onClick={() => navigate(`/news/${a.id}`)}
          >
            <div className="ad-news-events-list__meta">
              <Tag
                color={POLITICAL_CATEGORY_COLOR[a.event_category ?? ''] ?? 'default'}
                className="ad-mr-1"
              >
                {POLITICAL_CATEGORY_LABEL[a.event_category ?? ''] ?? a.event_category}
              </Tag>
              <Tooltip title={a.published_at}>
                <span className="ad-text-small ad-text-tertiary ad-news-events-list__time">
                  {new Date(a.published_at).toLocaleString('zh-CN', {
                    hour: '2-digit',
                    minute: '2-digit',
                    month: '2-digit',
                    day: '2-digit',
                  })}
                </span>
              </Tooltip>
            </div>
            <div className="ad-news-events-list__title">{a.title}</div>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export default function GlobalMarkets() {
  // AI Help wiring (M22-1): pass the current indicator rows plus the
  // most recent 5 political / macro news items into the help drawer
  // so the LLM has both market context and event context.
  const { open: openAIHelp } = useAIHelp();
  const { data: recentPoliticalData } = useRecentPoliticalEvents();

  // Fetch latest for both 'global' and 'us' so we can cover DXY,
  // USDJPY, Brent, WTI, Gold, SP500 *and* the legacy US series
  // (VIX, UST yields, Treasury spreads).
  const { data: latestGlobal, isLoading: gLoading } = useMacroLatest('global');
  const { data: latestUs, isLoading: uLoading } = useMacroLatest('us');

  const isLoading = gLoading || uLoading;
  const allLatest: MacroLatestItem[] = useMemo(
    () => [...(latestGlobal?.items ?? []), ...(latestUs?.items ?? [])],
    [latestGlobal, latestUs],
  );

  const [seriesByCode, setSeriesByCode] = useState<
    Record<string, MacroIndicatorSeries | null>
  >({});

  // Build a fast lookup: code -> latest MacroLatestItem.
  const latestByCode = useMemo(() => {
    const map: Record<string, MacroLatestItem> = {};
    for (const it of allLatest) map[it.code] = it;
    return map;
  }, [allLatest]);

  // Pull the recent series for each primary code so we can compute
  // day-over-day change and render a sparkline.  Runs once on mount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const out: Record<string, MacroIndicatorSeries | null> = {};
      await Promise.all(
        PRIMARY_CODES.map(async (code) => {
          try {
            const r = await macroApi.getSeries(code, { limit: 30 });
            if (cancelled) return;
            out[code] = (r.data as MacroIndicatorSeries) ?? null;
          } catch {
            if (!cancelled) out[code] = null;
          }
        }),
      );
      if (!cancelled) setSeriesByCode(out);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const rows: RowVm[] = useMemo(
    () =>
      PRIMARY_CODES.map((code) => {
        const series = seriesByCode[code] ?? null;
        const points = series?.points ?? [];
        const prev = points.length >= 2 ? points[points.length - 2].value : null;
        const latest = latestByCode[code];
        const lastN = points.slice(-30).map((p) => p.value);
        const lastPeriod =
          latest?.period ??
          (points.length > 0 ? points[points.length - 1].period : null);
        return {
          code,
          name: latest?.name_zh || code,
          region: latest?.region || 'global',
          unit: latest?.unit ?? '',
          latest: latest?.value ?? null,
          previous: prev,
          changePct:
            latest?.value != null && prev != null && prev !== 0
              ? ((latest.value - prev) / prev) * 100
              : null,
          asOf: lastPeriod,
          sparkline: lastN,
        };
      }),
    [seriesByCode, latestByCode],
  );

  const grouped: Array<{ key: string; label: string; rows: RowVm[] }> =
    useMemo(() => {
      const buckets: Record<string, RowVm[]> = {};
      for (const r of rows) {
        const key = inferCategoryKey(r.code);
        if (!buckets[key]) buckets[key] = [];
        buckets[key].push(r);
      }
      return CATEGORY_ORDER.filter((k) => buckets[k]?.length).map((k) => ({
        key: k,
        label: CATEGORY_LABELS[k] || k,
        rows: buckets[k],
      }));
    }, [rows]);

  const hasAnyData = rows.some(
    (r) => r.latest != null || (r.sparkline && r.sparkline.length > 0),
  );

  const handleOpenHelp = () => {
    // Build the indicator rows summary for the LLM context. Flatten
    // the grouped table into one row per code with its category so
    // the prompt can mention e.g. "VIX 32.1 (+18%)" without having to
    // re-walk the Table structure.
    const flatRows = rows.map((r) => ({
      ...r,
      category: inferCategoryKey(r.code),
    }));
    const recentEvents: NewsArticleSummary[] = (recentPoliticalData?.items ?? [])
      .slice(0, 5)
      .map((a: NewsArticle) => ({
        title: a.title,
        published_at: a.published_at,
        event_category: a.event_category ?? null,
        importance: a.importance ?? null,
        market: a.market,
        source: a.source,
        body: a.body ?? null,
      }));
    openAIHelp({
      pageType: 'global_markets',
      pageTitle: '全球市场速览',
      contextData: buildGlobalMarketsContext(flatRows, recentEvents),
      quickQuestions: getQuickQuestions('global_markets'),
      initialQuestion:
        '请基于当前页面指标和最近 24h 政治 / 地缘事件，帮我快速解读全球资本市场当前的状态，以及可能的传导路径。',
    });
  };

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="海外资本市场"
        title="全球市场速览"
        description={
          '汇总美债收益率曲线、美元指数、商品、外汇、主要指数与波动率（VIX）。数据来自 FRED (Federal Reserve Economic Data)，每个工作日 03:00 北京时间自动刷新；FRED API key 缺失时显示为空状态。'
        }
        extra={
          <>
            <HelpTrigger tooltip="AI 解读全球市场 + 最近地缘事件" onClick={handleOpenHelp} />
            <LastUpdated at={undefined} loading={isLoading} />
          </>
        }
      />

      <section className="phase5c-section">
        <Recent24hEvents />
      </section>

      {!hasAnyData && !isLoading && (
        <section className="phase5c-section">
          <Panel>
            <EmptyState
              title="暂无全球市场数据"
              description={
                'FRED 暂未拉取到任何全球指标。请确认服务器已配置 FRED_API_KEY，并等待下一次调度（默认每个工作日 03:00 北京时间）。'
              }
            />
          </Panel>
        </section>
      )}

      {isLoading && !hasAnyData && (
        <section className="phase5c-section">
          <Panel>
            <Skeleton active paragraph={{ rows: 8 }} />
          </Panel>
        </section>
      )}

      {hasAnyData &&
        grouped.map((g) => <CategoryBlock key={g.key} title={g.label} rows={g.rows} />)}
    </PageShell>
  );
}

