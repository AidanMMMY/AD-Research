/**
 * Global Markets page — covers overseas indices, US Treasury yields,
 * USD index, COMEX commodities and VIX.
 *
 * Data sources (Phase 5d, 2026-07-07):
 *  - FRED (region=us | global): US yields, DXY, USDJPY, Brent, WTI, SP500, Nasdaq, Dow.
 *  - yfinance (region=global, source=yfinance): Hang Seng, Nikkei 225,
 *    DAX, FTSE 100, CAC 40, ASX 200, KOSPI, TWSE, NIFTY 50, SENSEX.
 *  - akshare (region=global, source=akshare): 上证综指, 深证成指, 沪深300.
 *
 * Backed by `/macro/latest?region=global` and
 * `/macro/indicators/{code}`; both transparently serve any code
 * stored in the macro_indicator table, so the same React Query
 * pipeline powers FRED + yfinance + akshare rows.
 *
 * See docs/dev-notes/20260704-global-markets-roadmap.md.
 */

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import './styles.css';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useIsMobile } from '@/hooks/useBreakpoint';
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
import ThemeTag from '@/components/ThemeTag';
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

/**
 * Apple-style motion layer (scoped to this page):
 * - Response: feedback lands on pointer-down (:active, 0ms), release springs back.
 * - Springs: critically-damped-ish cubic-bezier; transform-only for frame smoothness.
 * - Typography: size-specific tracking (large tight, small loose).
 * - Reduced motion: cross-fade only, transforms disabled.
 */
const ADX_STYLE = `
.adx-global-markets {
  --adx-spring: cubic-bezier(0.5, 1.6, 0.3, 1);
  --adx-ease-out: cubic-bezier(0.22, 0.9, 0.3, 1);
}
.adx-global-markets .ant-btn,
.adx-global-markets .ad-news-events-list__item {
  touch-action: manipulation;
  transition: transform 240ms var(--adx-spring), background-color 140ms var(--adx-ease-out);
}
.adx-global-markets .ant-btn:active,
.adx-global-markets .ad-news-events-list__item:active {
  transform: scale(0.98);
  background-color: var(--bg-active);
  transition-duration: 0ms;
}
.adx-global-markets .ant-table-tbody > tr {
  transition: background-color 140ms var(--adx-ease-out);
}
.adx-global-markets h1,
.adx-global-markets h2,
.adx-global-markets .ant-typography h1,
.adx-global-markets .ant-typography h2 {
  letter-spacing: -0.02em;
  line-height: 1.18;
}
.adx-global-markets .ad-text-xs,
.adx-global-markets .ad-text-small {
  letter-spacing: 0.01em;
}
@media (prefers-reduced-motion: reduce) {
  .adx-global-markets *,
  .adx-global-markets *::before,
  .adx-global-markets *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }
  .adx-global-markets .ant-btn:active,
  .adx-global-markets .ad-news-events-list__item:active {
    transform: none;
  }
}
`;

function AdxShell({ children }: { children: ReactNode }) {
  return (
    <div className="adx-global-markets">
      <style>{ADX_STYLE}</style>
      {children}
    </div>
  );
}

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

/** Codes we want to surface on the Global Markets page (in display order).
 *
 *  Coverage by source:
 *  - FRED (`source=fred`): us_dgs*, us_t10y*, global_dxy, global_usdjpy,
 *    global_brent, global_wti, global_sp500, global_nasdaq, global_dow,
 *    us_vix, usd_eur, usd_cny.
 *  - yfinance (`source=yfinance`): global_hsi, global_n225,
 *    global_dax, global_ftse, global_cac, global_asx, global_kospi,
 *    global_twse, global_nifty, global_sensex.
 *  - akshare (`source=akshare`): global_shcomp, global_szse,
 *    global_csi300.
 *
 *  Codes are pulled from both regions (``us`` + ``global``) — see
 *  ``useMacroLatest('us' | 'global')`` calls below.
 *
 *  FRED coverage note (2026-07-07):
 *  - ✅ Have free series: DXY, USDJPY, USDEUR, USDCNY, UST yields,
 *    WTI/Brent, SP500/Nasdaq/Dow, VIX.
 *  - ❌ No free FRED series for: DAX, FTSE, CAC, NIFTY, SENSEX, KOSPI,
 *    TWSE, SHCOMP, SZE, ASX, Nikkei, Hang Seng. Gold (GOLDAMGBD228NLBM)
 *    was discontinued with no direct replacement.
 *    As of 2026-07-07, the yfinance + akshare pipeline now covers
 *    the international index gap (see
 *    ``app/services/macro/global_indices_fetcher.py``).
 */
const PRIMARY_CODES: string[] = [
  // ── Rates (UST curve + policy) ──
  'us_dgs30',
  'us_dgs10',
  'us_dgs2',
  'us_t10y2y',
  'us_t10y3m',
  // ── FX (broad USD + major crosses) ──
  'global_dxy',
  'global_usdjpy',
  'usd_eur',
  'usd_cny',
  // ── Commodities ──
  'global_brent',
  'global_wti',
  // NOTE: FRED discontinued the free gold series (GOLDAMGBD228NLBM). Gold
  // is hidden until a replacement commodity source is wired.
  // 'global_gold',
  // ── Cross-border Index (US — FRED) ──
  'global_sp500',
  'global_nasdaq',
  'global_dow',
  // ── A-share (akshare) ──
  'global_shcomp',
  'global_szse',
  'global_csi300',
  // ── International (yfinance) — Asia Pacific ──
  'global_hsi',
  'global_n225',
  'global_kospi',
  'global_twse',
  'global_asx',
  // ── International (yfinance) — Europe ──
  'global_dax',
  'global_ftse',
  'global_cac',
  // ── International (yfinance) — India ──
  'global_nifty',
  'global_sensex',
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
 *
 * ``usd_*`` codes live in the ``us`` region (see FredService.SERIES_REGISTRY
 * FX block) but are conceptually FX, so we route them to the ``fx``
 * bucket regardless of the prefix.
 *
 * As of Phase 5d (2026-07-07) every ``global_*`` index code
 * (FRED + yfinance + akshare) collapses into the ``index`` bucket
 * via the fallback return — adding a new international index only
 * requires adding the code to PRIMARY_CODES; no further mapping
 * change is needed.
 */
function inferCategoryKey(code: string): string {
  if (code.startsWith('us_dgs') || code.startsWith('us_t10y')) return 'rate';
  if (code === 'us_vix') return 'vol';
  if (
    code.startsWith('global_dxy') ||
    code.startsWith('global_usdjpy') ||
    code.startsWith('usd_')
  )
    return 'fx';
  if (code.startsWith('global_brent') || code.startsWith('global_wti')) return 'commodity';
  // Everything else global_* falls into the index bucket — covers
  // FRED SP500/Nasdaq/Dow, yfinance HSI/N225/DAX/FTSE/CAC/ASX/KOSPI/
  // TWSE/NIFTY/SENSEX, and akshare SHCOMP/SZSE/CSI300.
  return 'index';
}

function CategoryBlock({ title, rows, isMobile }: { title: string; rows: RowVm[]; isMobile: boolean }): JSX.Element | null {
  if (rows.length === 0) return null;
  const columns: ColumnsType<RowVm> = [
    {
      title: '指标',
      dataIndex: 'name',
      key: 'name',
      width: isMobile ? 120 : 220,
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
      width: isMobile ? 80 : 140,
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
      width: isMobile ? 70 : 110,
      align: 'right',
      render: (v: number | null) =>
        v == null ? <Text type="secondary">—</Text> : <ReturnTag value={v} />,
    },
    {
      title: '近30日',
      dataIndex: 'sparkline',
      key: 'sparkline',
      width: isMobile ? 80 : 160,
      render: (s: number[]) =>
        s.length >= 2 ? (
          <Sparkline data={s} width={isMobile ? 70 : 140} height={isMobile ? 20 : 26} />
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: '数据日期',
      dataIndex: 'asOf',
      key: 'asOf',
      width: isMobile ? 0 : 130,
      className: isMobile ? 'ad-hidden-mobile' : undefined,
      render: (p: string | null) =>
        p ? <Text type="secondary">{p}</Text> : <Text type="secondary">未采集</Text>,
    },
    {
      title: '区域',
      dataIndex: 'region',
      key: 'region',
      width: isMobile ? 0 : 90,
      className: isMobile ? 'ad-hidden-mobile' : undefined,
      render: (r: string) =>
        r === 'global' ? <ThemeTag variant="neutral">全球</ThemeTag> : <ThemeTag variant="accent">美国</ThemeTag>,
    },
  ];
  return (
    <section className="ad-section">
      <SectionHeading title={title} />
      <Panel>
        <div className="ad-table-scroll">
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
// Recent-week political / macro event stream (K12, 2026-07-04).
//
// Reuses the new ``event_category`` filter from the News API to surface
// geopolitics / central_bank / election / trade_war / sanction items in
// the last 7 days at importance >= 4. Each row links into the News
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
 * the last 7 days with importance >= 4.  Lives at module scope so both
 * the on-page widget and the AI Help button consume the same cache
 * entry (and we only hit /news once per minute).
 */
function useRecentPoliticalEvents() {
  const since = useMemo(
    () => new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
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
 * Compact "recent week political events" panel. Renders nothing while
 * loading (so the rest of the page is not blocked), then either a
 * 5-row clickable list or an empty-state message.  The query lives in
 * ``useRecentPoliticalEvents`` so the AI Help button can reuse the
 * same cache entry.
 */
function RecentWeekEvents(): JSX.Element | null {
  const navigate = useNavigate();
  const { data, isLoading, isError } = useRecentPoliticalEvents();

  if (isLoading) {
    return (
      <Panel title="最近一周重大政治 / 地缘事件" padding="md">
        <Skeleton active paragraph={{ rows: 3 }} />
      </Panel>
    );
  }
  if (isError) {
    return (
      <Panel title="最近一周重大政治 / 地缘事件" padding="md">
        <EmptyState title="事件流加载失败" />
      </Panel>
    );
  }
  const items: NewsArticle[] = data?.items ?? [];
  if (items.length === 0) {
    return (
      <Panel title="最近一周重大政治 / 地缘事件" padding="md">
        <EmptyState
          title="暂无近一周内重大政治事件"
          description="一旦 LLM 抽取到 importance>=4 的地缘 / 央行 / 选举 / 贸易战 / 制裁事件，会在这里显示。"
        />
      </Panel>
    );
  }

  return (
    <Panel title="最近一周重大政治 / 地缘事件" padding="md">
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
  const isMobile = useIsMobile();
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
        '请基于当前页面指标和最近一周政治 / 地缘事件，帮我快速解读全球资本市场当前的状态，以及可能的传导路径。',
    });
  };

  return (
    <AdxShell>
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

      <section className="ad-section">
        <RecentWeekEvents />
      </section>

      {!hasAnyData && !isLoading && (
        <section className="ad-section">
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
        <section className="ad-section">
          <Panel>
            <Skeleton active paragraph={{ rows: 8 }} />
          </Panel>
        </section>
      )}

      {hasAnyData &&
        grouped.map((g) => <CategoryBlock key={g.key} title={g.label} rows={g.rows} isMobile={isMobile} />)}
    </PageShell>
    </AdxShell>
  );
}

