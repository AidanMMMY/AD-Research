import { useMemo, useState } from 'react';
import {
  Row,
  Col,
  Table,
  Select,
  Spin,
  Alert,
  Space,
  Typography,
  Button,
  Skeleton,
  message,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import StatCard from '@/components/StatCard';
import EmptyState from '@/components/EmptyState';
import FilterToolbar from '@/components/FilterToolbar';
import LastUpdated from '@/components/LastUpdated';
import HelpPopover from '@/components/HelpPopover';
import ThemeTag from '@/components/ThemeTag';
import { useSettingsStore } from '@/stores/settings';
import { useMacroIndicators, useMacroSeries } from '@/hooks/useMacro';
import {
  useMacroLatest,
  useRefreshChinaMacro,
} from '@/api/macro';
import type { MacroIndicatorItem, MacroLatestItem } from '@/api/macro';

const { Text } = Typography;

const REGION_OPTIONS = [
  { value: 'us', label: '美国 (FRED)' },
  { value: 'cn', label: '中国 (akshare)' },
  { value: 'global', label: '全球' },
];

const MACRO_TERM_KEY_MAP: Record<string, string> = {
  us_cpi: 'cpi',
  cpi_yoy: 'cpi',
  us_unrate: 'unemployment_rate',
  us_fed_funds: 'fed_funds',
  us_dgs10: 'treasury_yield',
  us_vix: 'vix',
  gdp_yoy: 'gdp',
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
  cn: ['gdp_yoy', 'cpi_yoy', 'ppi_yoy', 'm2_yoy', 'pmi_manufacturing', 'shibor_3m'],
  global: [],
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
  const [region, setRegion] = useState<string>('us');
  const [selectedCode, setSelectedCode] = useState<string | null>(null);

  const { data: indicators, isLoading, error } = useMacroIndicators(region);
  const { data: series, isLoading: seriesLoading } = useMacroSeries(selectedCode, {
    limit: 365,
  });
  const { data: latestData, dataUpdatedAt, isFetching: latestFetching } = useMacroLatest(
    region === 'us' ? undefined : region,
  );
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

  const description = useMemo(() => {
    if (region === 'cn') {
      return '由 akshare 抓取 NBS / PBOC / SHIBOR 等公开数据，覆盖 GDP / CPI / PPI / M2 / PMI / SHIBOR / 存款准备金率 等关键指标。每个工作日 09:30 北京时间自动刷新。';
    }
    return '由 FRED (Federal Reserve Economic Data) 提供，覆盖 GDP / CPI / 失业率 / 国债收益率 / VIX 等 20+ 关键指标。每个工作日 03:00 北京时间自动刷新。';
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
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 90,
      render: (cat?: string) =>
        cat ? <ThemeTag variant="accent">{cat}</ThemeTag> : <Text type="secondary">—</Text>,
    },
    {
      title: '最新值',
      dataIndex: 'value',
      key: 'value',
      width: 120,
      align: 'right',
      render: (v: number | null, row) => (
        <Text strong>{formatValue(v, row.unit)}</Text>
      ),
    },
    {
      title: '单位',
      dataIndex: 'unit',
      key: 'unit',
      width: 110,
      render: (u: string) => <Text type="secondary">{u || '—'}</Text>,
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
      render: (_, row) => (
        <a onClick={() => setSelectedCode(row.code)}>查看走势</a>
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
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="宏观指标"
        title={region === 'cn' ? '中国宏观看板' : '美国宏观看板'}
        description={description}
        extra={
          <Space size="middle">
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
        <div className="phase5c-section">
          <Alert
            type="error"
            showIcon
            message="加载宏观指标失败"
            description={(error as Error).message}
          />
        </div>
      )}

      {/* ── Headline KPI strip ── */}
      {headlineLoading ? (
        <div className="phase5c-section">
          <Row gutter={[16, 16]}>
            {HEADLINE_CODES[region]?.map((code) => (
              <Col xs={12} md={8} lg={4} key={code}>
                <Skeleton active paragraph={{ rows: 2 }} />
              </Col>
            ))}
          </Row>
        </div>
      ) : headline.length > 0 ? (
        <div className="phase5c-section">
          <Row gutter={[16, 16]}>
            {headline.map((item) => (
              <Col xs={12} md={8} lg={Math.max(4, 24 / headline.length)} key={item.code}>
                <StatCard
                  title={
                    MACRO_TERM_KEY_MAP[item.code] ? (
                      <HelpPopover termKey={MACRO_TERM_KEY_MAP[item.code]} mode={mode}>{item.name_zh}</HelpPopover>
                    ) : item.name_zh
                  }
                  value={formatValue(item.value, item.unit)}
                  suffix={item.period ? `${item.period}` : undefined}
                />
              </Col>
            ))}
          </Row>
        </div>
      ) : null}

      <FilterToolbar total={indicators?.length}>
        <Select
          value={region}
          onChange={(v) => {
            setRegion(v);
            setSelectedCode(null);
          }}
          options={REGION_OPTIONS}
          style={{ width: 180 }}
        />
      </FilterToolbar>

      <Row gutter={[16, 16]}>
        {/* ── Indicator list ── */}
        <Col xs={24} lg={selectedCode ? 12 : 24}>
          <Panel title="全部指标">
            <Spin spinning={isLoading}>
              <div className="ad-density-dense ad-table-scroll ad-table-sticky">
                <Table<MacroIndicatorItem>
                  rowKey="code"
                  size="small"
                  dataSource={indicators ?? []}
                  columns={columns}
                  pagination={{ pageSize: 15, showSizeChanger: false }}
                  onRow={(record) => ({
                    onClick: () => setSelectedCode(record.code),
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
        {selectedCode && (
          <Col xs={24} lg={12}>
            <Panel
              title={series ? `${series.name_zh} · 走势` : '走势'}
              extra={<a onClick={() => setSelectedCode(null)}>关闭</a>}
            >
              <Spin spinning={seriesLoading}>
                {chartOption ? (
                  <div className="ad-chart-container ad-chart-container--tall">
                    <ReactECharts option={chartOption} notMerge />
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
  );
}
