import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import './styles.css';
import {
  Row,
  Col,
  Table,
  Segmented,
  Spin,
  Alert,
  Space,
  Typography,
  Button,
  Skeleton,
  message,
  Tooltip,
} from 'antd';
import {
  ReloadOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import StatCard from '@/components/StatCard';
import SectionHeading from '@/components/SectionHeading';
import EmptyState from '@/components/EmptyState';
import FilterToolbar from '@/components/FilterToolbar';
import LastUpdated from '@/components/LastUpdated';
import HelpPopover from '@/components/HelpPopover';
import { useSettingsStore } from '@/stores/settings';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';
import { useMacroIndicators, useMacroSeries } from '@/hooks/useMacro';
import {
  useMacroLatest,
  useRefreshChinaMacro,
} from '@/api/macro';
import type { MacroIndicatorItem, MacroLatestItem } from '@/api/macro';

/**
 * Apple-style motion layer (scoped to this page):
 * - Response: feedback lands on pointer-down (:active, 0ms), release springs back.
 * - Springs: critically-damped-ish cubic-bezier; transform-only for frame smoothness.
 * - Spatial consistency: the chart panel materializes (scale+fade) from its anchor.
 * - Typography: size-specific tracking (large tight, small loose).
 * - Reduced motion: cross-fade only, transforms disabled.
 */
const ADX_STYLE = `
.adx-macro {
  /* Critically-damped monotonic curve: y2 ≤ 1, no overshoot. */
  --adx-spring: cubic-bezier(0.32, 0.72, 0, 1);
  --adx-ease-out: cubic-bezier(0.22, 0.9, 0.3, 1);
}
.adx-macro .ant-btn {
  touch-action: manipulation;
  transition: transform 240ms var(--adx-spring), background-color 140ms var(--adx-ease-out);
}
.adx-macro .ant-btn:active {
  transform: scale(0.97);
  transition-duration: 0ms;
}
.adx-macro .ant-segmented-item {
  touch-action: manipulation;
  transition: color 140ms var(--adx-ease-out);
}
.adx-macro .ant-table-tbody > tr {
  touch-action: manipulation;
  transition: background-color 140ms var(--adx-ease-out);
}
.adx-macro .ant-table-tbody > tr:active {
  background-color: var(--bg-active);
  transition-duration: 0ms;
}
@keyframes adx-macro-materialize {
  from { opacity: 0; transform: translateY(8px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes adx-macro-dematerialize {
  from { opacity: 1; transform: translateY(0) scale(1); }
  to { opacity: 0; transform: translateY(8px) scale(0.98); }
}
.adx-macro .adx-materialize {
  transform-origin: top center;
  animation: adx-macro-materialize 320ms var(--adx-spring) both;
}
.adx-macro .adx-materialize--exit {
  transform-origin: top center;
  animation: adx-macro-dematerialize 220ms var(--adx-spring) both;
}
.adx-macro h1,
.adx-macro h2,
.adx-macro .ant-typography h1,
.adx-macro .ant-typography h2 {
  letter-spacing: -0.02em;
  line-height: 1.18;
}
.adx-macro .ad-text-xs,
.adx-macro .ad-text-small {
  letter-spacing: 0.01em;
}
@media (prefers-reduced-motion: reduce) {
  .adx-macro *,
  .adx-macro *::before,
  .adx-macro *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }
  .adx-macro .ant-btn:active {
    transform: none;
  }
  .adx-macro .adx-materialize {
    animation: none;
  }
  .adx-macro .adx-materialize--exit {
    animation: none;
  }
}
`;

function AdxShell({ children }: { children: ReactNode }) {
  return (
    <div className="adx-macro">
      <style>{ADX_STYLE}</style>
      {children}
    </div>
  );
}

const { Text } = Typography;

const REGION_OPTIONS = [
  { value: 'us', label: '美国' },
  { value: 'eu', label: '欧元区' },
  { value: 'cn', label: '中国' },
  { value: 'global', label: '全球' },
];

const MACRO_TERM_KEY_MAP: Record<string, string> = {
  us_cpi: 'cpi',
  cpi_yoy: 'cpi',
  eu_cpi: 'cpi',
  us_unrate: 'unemployment_rate',
  eu_unrate: 'unemployment_rate',
  us_fed_funds: 'fed_funds',
  us_dgs10: 'treasury_yield',
  us_vix: 'vix',
  gdp_yoy: 'gdp',
  eu_gdp: 'gdp',
  ppi_yoy: 'ppi',
  m2_yoy: 'm2',
  pmi_manufacturing: 'pmi',
  shibor_3m: 'shibor',
};

/**
 * Format a numeric value for display.  Rates stay as-is, big numbers
 * get a thousands separator, percentages get one decimal.
 */
function formatValue(v: number | null | undefined, unit: string): string {
  if (v == null || Number.isNaN(v)) return '—';
  if (unit === '%') return `${v.toFixed(2)}%`;
  if (Math.abs(v) >= 1000) {
    return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return v.toFixed(2);
}

// Headline KPIs per region. Order = display order in the strip.
const HEADLINE_CODES: Record<string, string[]> = {
  us: ['us_cpi', 'us_unrate', 'us_fed_funds', 'us_dgs10', 'us_vix'],
  eu: ['eu_cpi', 'eu_unrate', 'eu_ecb_deposit_rate', 'eu_gdp'],
  cn: ['gdp_yoy', 'cpi_yoy', 'ppi_yoy', 'm2_yoy', 'pmi_manufacturing', 'shibor_3m'],
  global: [
    'global_sp500', 'global_nasdaq', 'global_dow', 'global_dxy',
    'global_brent', 'global_wti', 'global_shcomp', 'global_hsi',
    'global_n225', 'global_szse',
  ],
};

// Headline cards for CN cannot be derived from the FRED-backed list
// (those indicators only exist in the akshare feed), so we surface them
// directly from the ``/macro/latest`` endpoint.
function buildCnHeadlineFromLatest(items: MacroLatestItem[]): MacroIndicatorItem[] {
  const wanted = HEADLINE_CODES.cn;
  return wanted
    .map((code) => items.find((i) => i.code === code))
    .filter((x): x is MacroLatestItem => !!x)
    .map<MacroIndicatorItem>((it) => ({
      code: it.code,
      region: it.region,
      name_zh: it.name_zh,
      name_en: it.name_en,
      unit: it.unit ?? '',
      source: it.source,
      period: it.period,
      value: it.value,
      fetched_at: it.fetched_at,
    }));
}

export default function Macro() {
  const mode = useSettingsStore((s) => s.mode);
  const prefersReducedMotion = usePrefersReducedMotion();
  // Initialize region / selectedCode from URL search params so deep-links
  // from Dashboard's Market Pulse tiles (e.g. /macro?region=global&code=global_sp500)
  // land on the right panel without a manual region switch.
  const [searchParams, setSearchParams] = useSearchParams();
  const urlRegion = searchParams.get('region');
  const urlCode = searchParams.get('code');
  const initialRegion: 'us' | 'eu' | 'cn' | 'global' =
    urlRegion === 'us' || urlRegion === 'eu' || urlRegion === 'cn' || urlRegion === 'global'
      ? urlRegion
      : 'us';
  const initialCode = urlCode;
  const [region, setRegion] = useState<string>(initialRegion);
  const [selectedCode, setSelectedCode] = useState<string | null>(initialCode);
  // Mirror region / selectedCode into the URL so deep-links stay shareable
  // and back/forward navigation works. We omit the region param when it
  // equals the default ('us') to keep URLs short.
  useEffect(() => {
    const next = new URLSearchParams();
    if (region !== 'us') next.set('region', region);
    if (selectedCode) next.set('code', selectedCode);
    setSearchParams(next, { replace: true });
  }, [region, selectedCode, setSearchParams]);
  // Mirror the chart-panel mount life-cycle so the exit animation can play
  // before the panel is actually unmounted (spatial consistency: enter
  // and exit use the same spring path).
  const [mountedCode, setMountedCode] = useState<string | null>(null);
  const [isExiting, setIsExiting] = useState(false);
  const exitTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (selectedCode) {
      // Entering (or switching chart): mount immediately, no exit animation.
      if (exitTimerRef.current != null) {
        window.clearTimeout(exitTimerRef.current);
        exitTimerRef.current = null;
      }
      setIsExiting(false);
      setMountedCode(selectedCode);
    } else if (mountedCode) {
      // Leaving: keep the mounted panel visible long enough for the
      // dematerialize keyframe (220ms) to play before unmounting.
      setIsExiting(true);
      exitTimerRef.current = window.setTimeout(() => {
        setMountedCode(null);
        setIsExiting(false);
        exitTimerRef.current = null;
      }, 220);
    }
    return () => {
      if (exitTimerRef.current != null) {
        window.clearTimeout(exitTimerRef.current);
        exitTimerRef.current = null;
      }
    };
  }, [selectedCode, mountedCode]);

  const { data: indicators, isLoading, error } = useMacroIndicators(region);
  const { data: series, isLoading: seriesLoading } = useMacroSeries(mountedCode, {
    limit: 365,
  });
  const { data: latestData, dataUpdatedAt, isFetching: latestFetching } = useMacroLatest(region);
  const refreshMutation = useRefreshChinaMacro();

  // ── KPIs: pick a few headline indicators per region ──
  const headlineCodesForRegion = HEADLINE_CODES[region] ?? [];
  const headline: MacroIndicatorItem[] = useMemo(() => {
    if (region === 'cn') {
      return buildCnHeadlineFromLatest(latestData?.items ?? []);
    }
    const all = indicators ?? [];
    return headlineCodesForRegion
      .map((code) => all.find((i) => i.code === code))
      .filter((x): x is MacroIndicatorItem => !!x);
  }, [region, indicators, latestData, headlineCodesForRegion]);

  // FRED freshness hints — keyed by code so each headline KPI tile can
  // surface the small "数据延迟" badge when its underlying row is FRED
  // and lags today by more than one day. The hint copy is owned by the
  // backend so Dashboard and Macro show the same wording.
  const freshnessHints = useMemo(() => {
    const map = new Map<string, string>();
    for (const it of latestData?.items ?? []) {
      if (it.freshness_hint) map.set(it.code, it.freshness_hint);
    }
    return map;
  }, [latestData]);

  const description = useMemo(() => {
    switch (region) {
      case 'cn':
        return '由 akshare 抓取 NBS / PBOC / SHIBOR 等公开数据，覆盖 GDP / CPI / PPI / M2 / PMI / SHIBOR / 存款准备金率 等关键指标。每个工作日 09:30 北京时间自动刷新。';
      case 'eu':
        return '由 FRED 提供欧元区宏观指标，覆盖 GDP / CPI / 失业率 / 欧央行政策利率 等关键指标。随美国宏观刷新任务每个工作日 03:00 北京时间自动刷新。';
      case 'global':
        return '由 FRED 提供跨境市场指标，覆盖全球主要股指、美元指数、美元兑日元、原油等。随美国宏观刷新任务每个工作日 03:00 北京时间自动刷新。';
      default:
        return '由 FRED (Federal Reserve Economic Data) 提供，覆盖 GDP / CPI / 失业率 / 国债收益率 / VIX 等 20+ 关键指标。每个工作日 03:00 北京时间自动刷新。';
    }
  }, [region]);

  const handleRefresh = async () => {
    try {
      const res = await refreshMutation.mutateAsync();
      message.success(
        `中国宏观刷新完成: 写入 ${res.written} 条 (${res.fetched} 条观测, 失败 ${res.failed.length} 项)`,
      );
    } catch (err: any) {
      const detail = err?.response?.data?.detail ?? '刷新失败';
      message.error(detail);
    }
  };

  // ── Table columns ──
  const columns: ColumnsType<MacroIndicatorItem> = [
    {
      title: '指标',
      dataIndex: 'name_zh',
      key: 'name_zh',
      width: 200,
      fixed: 'left',
      render: (name: string, row) => (
        <Space direction="vertical" size={0}>
          <Text strong>{name}</Text>
          {row.name_en && (
            <Text type="secondary" className="ad-text-xs">
              {row.name_en}
            </Text>
          )}
        </Space>
      ),
    },
    {
      title: '最新值',
      dataIndex: 'value',
      key: 'value',
      width: 140,
      align: 'right',
      sorter: (a, b) => (a.value ?? -Infinity) - (b.value ?? -Infinity),
      render: (v: number | null, row) => (
        <Text strong>{formatValue(v, row.unit)}</Text>
      ),
    },
    {
      title: '最新期',
      dataIndex: 'period',
      key: 'period',
      width: 120,
      render: (p?: string | null) =>
        p ? <Text>{p}</Text> : <Text type="secondary">未采集</Text>,
    },
    {
      title: '更新时间',
      dataIndex: 'fetched_at',
      key: 'fetched_at',
      width: 180,
      render: (t?: string | null) =>
        t ? (
          <Text type="secondary" className="ad-text-xs">
            {new Date(t).toLocaleString()}
          </Text>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      fixed: 'right',
      render: (_, row) => (
        <Button
          type="link"
          size="small"
          onClick={() => setSelectedCode(row.code)}
          aria-label={`查看 ${row.name_zh ?? row.code} 的走势`}
        >
          查看走势
        </Button>
      ),
    },
  ];

  // ── Chart option ──
  const chartOption: EChartsOption | null = useMemo(() => {
    if (!series || !series.points.length) return null;
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 60, right: 20, top: 30, bottom: 50 },
      xAxis: {
        type: 'category',
        data: series.points.map((p) => p.period),
        axisLabel: { rotate: 45, fontSize: 10 },
      },
      yAxis: {
        type: 'value',
        name: series.unit,
        axisLabel: { fontSize: 11 },
      },
      series: [
        {
          type: 'line',
          smooth: true,
          showSymbol: false,
          data: series.points.map((p) => p.value),
          lineStyle: { width: 2 },
          areaStyle: { opacity: 0.1 },
        },
      ],
    };
  }, [series]);

  const headlineLoading = region === 'cn' ? latestFetching && !latestData : isLoading;

  return (
    <AdxShell>
      <PageShell maxWidth="wide">
        <PageHeader
          eyebrow="宏观指标"
        title={
          {
            cn: '中国宏观看板',
            eu: '欧元区宏观看板',
            global: '全球跨市场指标',
            us: '美国宏观看板',
          }[region] ?? '美国宏观看板'
        }
        description={description}
        extra={
          <Space size="middle" wrap>
            <Segmented
              value={region}
              onChange={(v) => {
                setRegion(v);
                // Keep selectedCode so deep-linked series still renders after a
                // region switch — useMacroSeries will hit FredService ->
                // MacroDataService fallback if the code isn't in the current
                // region's headline list.
              }}
              options={REGION_OPTIONS}
            />
            <LastUpdated at={dataUpdatedAt} loading={latestFetching && !latestData} />
            {region === 'cn' && (
              <Button
                icon={<ReloadOutlined />}
                loading={refreshMutation.isPending}
                onClick={handleRefresh}
              >
                刷新
              </Button>
            )}
          </Space>
        }
      />

      {error && (
        <Alert
          type="error"
          showIcon
          message="加载宏观指标失败"
          description={(error as Error).message}
          className="ad-mb-5"
        />
      )}

      {/* ── Headline KPI strip ── */}
      <SectionHeading title="头条指标" />
      {headlineLoading ? (
        <Row gutter={[16, 16]} className="ad-mb-5">
          {HEADLINE_CODES[region]?.map((code) => (
            <Col xs={12} md={8} lg={4} key={code}>
              <Skeleton active paragraph={{ rows: 2 }} />
            </Col>
          ))}
        </Row>
      ) : headline.length > 0 ? (
        <Row gutter={[16, 16]} className="ad-mb-5">
          {headline.map((item) => {
            const hint = freshnessHints.get(item.code) ?? null;
            return (
              <Col xs={12} md={8} lg={Math.max(4, 24 / headline.length)} key={item.code}>
                <div className="ad-relative">
                  {hint ? (
                    <Tooltip title={hint}>
                      <span
                        className="macro__freshness-badge"
                        aria-label={hint}
                      >
                        <ExclamationCircleOutlined className="macro__freshness-badge__icon" />
                        <span className="macro__freshness-badge__label">数据延迟</span>
                      </span>
                    </Tooltip>
                  ) : null}
                  <StatCard
                    title={
                      MACRO_TERM_KEY_MAP[item.code] ? (
                        <HelpPopover termKey={MACRO_TERM_KEY_MAP[item.code]} mode={mode}>{item.name_zh}</HelpPopover>
                      ) : item.name_zh
                    }
                    value={formatValue(item.value, item.unit)}
                    suffix={item.period ? `${item.period}` : undefined}
                  />
                </div>
              </Col>
            );
          })}
        </Row>
      ) : null}

      <FilterToolbar total={indicators?.length} />

      <Row gutter={[16, 16]}>
        {/* ── Indicator list ── */}
        <Col xs={24} lg={mountedCode ? 12 : 24}>
          <Panel title="全部指标">
            <Spin spinning={isLoading}>
              <div className="ad-table-scroll ad-table-sticky">
                <Table<MacroIndicatorItem>
                  rowKey="code"
                  size="small"
                  dataSource={indicators ?? []}
                  columns={columns}
                  scroll={{ x: 'max-content' }}
                  pagination={{ pageSize: 15, showSizeChanger: false }}
                  onRow={(record) => ({
                    onClick: () => setSelectedCode(record.code),
                    onKeyDown: (e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        setSelectedCode(record.code);
                      }
                    },
                    tabIndex: 0,
                    role: 'button',
                    'aria-label': `查看 ${record.name_zh ?? record.code} 的走势`,
                  })}
                  locale={{
                    emptyText: isLoading ? '加载中...' : <EmptyState title="暂无指标数据" />,
                  }}
                />
              </div>
            </Spin>
          </Panel>
        </Col>

        {/* ── Chart panel ── */}
        {mountedCode && (
          <Col
            xs={24}
            lg={12}
            className={isExiting ? 'adx-materialize adx-materialize--exit' : 'adx-materialize'}
            aria-hidden={isExiting}
          >
            <Panel
              title={series ? `${series.name_zh} · 走势` : '走势'}
              extra={
                <Button
                  type="link"
                  size="small"
                  onClick={() => setSelectedCode(null)}
                  aria-label="关闭走势面板"
                >
                  关闭
                </Button>
              }
            >
              <Spin spinning={seriesLoading}>
                {chartOption ? (
                  <div className="ad-chart-container ad-chart-container--tall">
                    <ReactECharts
                      option={{
                        ...chartOption,
                        animation: !prefersReducedMotion,
                      }}
                      notMerge
                    />
                  </div>
                ) : (
                  <EmptyState title="暂无历史数据" />
                )}
                {series && series.points.length > 0 && (
                  <div className="ad-mt-3 ad-timestamp">
                    共 {series.points.length} 个观测点 · 最近一期：
                    {series.points[series.points.length - 1].period}
                    （{formatValue(series.points[series.points.length - 1].value, series.unit)}）
                  </div>
                )}
              </Spin>
            </Panel>
          </Col>
        )}
      </Row>
      </PageShell>
    </AdxShell>
  );
}
