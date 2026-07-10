import { useEffect, useMemo, useState } from 'react';
import { Alert, Segmented, Select, Spin, Table, Tabs, Tag } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import {
  useSectorConstituents,
  useSectorList,
  useSectorRotation,
} from '@/hooks/useSectorRotation';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import EmptyState from '@/components/EmptyState';
import HelpPopover from '@/components/HelpPopover';
import LastUpdated from '@/components/LastUpdated';
import ReturnTag from '@/components/ReturnTag';
import ThemeTag from '@/components/ThemeTag';
import { useSettingsStore } from '@/stores/settings';
import { getReturnColor } from '@/utils/color';
import { resolveChartColors } from '@/utils/cssVar';
import type {
  SectorClassification,
  SectorConstituent,
  SectorPerformance,
  SectorReturnPeriod,
} from '@/types/sector_rotation';
import { SECTOR_RETURN_LABELS, SECTOR_RETURN_PERIODS } from '@/types/sector_rotation';
import './styles.css';

const PERIOD_RETURN_KEY: Record<SectorReturnPeriod, keyof SectorPerformance> = {
  '1w': 'return_1w',
  '1m': 'return_1m',
  '3m': 'return_3m',
  '6m': 'return_6m',
  '1y': 'return_1y',
};

/**
 * Normalise a CSS variable colour ("var(--color-rise)") to its terminal
 * hex fallback for ECharts (which can't resolve CSS vars inside dynamic
 * style props). Falls back to the chart palette utility.
 */
function toEChartsColor(cssVarRef: string, fallback: string): string {
  const [resolved] = resolveChartColors([cssVarRef], [fallback]);
  return resolved;
}

// Detail-panel tab keys (板块汇总 / 成份股构成).
type DetailTab = 'summary' | 'constituents';

export default function SectorRotation() {
  const mode = useSettingsStore((s) => s.mode);
  // Industry taxonomy toggle: GICS (global default) vs 申万一级 (A-share).
  const [classification, setClassification] = useState<SectorClassification>('GICS');
  const clsLabel = classification === 'SW' ? '申万一级' : 'GICS';
  const { data, isLoading, isFetching, dataUpdatedAt } = useSectorRotation(
    undefined,
    undefined,
    classification,
  );
  // Sector list (for the constituents tab's dropdown).
  const { data: sectorsData } = useSectorList(classification);
  // Detail-panel tab (板块汇总 / 成份股构成).
  const [detailTab, setDetailTab] = useState<DetailTab>('summary');
  // Re-render when the theme toggles so chart colours pick up new vars.
  const [, setThemeTick] = useState(0);
  useEffect(() => {
    const handler = () => setThemeTick((t) => t + 1);
    document.addEventListener('themechange', handler);
    return () => document.removeEventListener('themechange', handler);
  }, []);

  const sectors = data?.sectors || [];
  const signals = data?.rotation_signals || [];
  const marketAvg = data?.market_avg;
  const scope = data?.scope;

  // Pre-resolve palette for heatmap once per render.
  const palette = useMemo(() => {
    const upHex = toEChartsColor('var(--color-rise)', '#c96b6b');
    const downHex = toEChartsColor('var(--color-fall)', '#5fa87a');
    const textPrimary = toEChartsColor('var(--text-primary)', '#1f1f1f');
    const textSecondary = toEChartsColor('var(--text-secondary)', '#666666');
    const border = toEChartsColor('var(--border-default)', 'rgba(0,0,0,0.08)');
    return { upHex, downHex, textPrimary, textSecondary, border };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ------------------ Charts ------------------

  /** Horizontal bar — sectors ranked by 1m return (best on top). */
  const rankOption: EChartsOption = useMemo(() => {
    const ordered = [...sectors].reverse(); // ECharts draws first at the bottom
    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        backgroundColor: '#fff',
        textStyle: { color: '#222' },
      },
      grid: { left: 130, right: 32, top: 20, bottom: 28 },
      xAxis: {
        type: 'value',
        axisLabel: { formatter: '{value}%', color: palette.textSecondary },
        splitLine: { lineStyle: { color: palette.border } },
      },
      yAxis: {
        type: 'category',
        data: ordered.map((s) => s.sector),
        axisLabel: { color: palette.textPrimary, fontSize: 12 },
      },
      series: [
        {
          type: 'bar',
          data: ordered.map((s) => ({
            value: s.return_1m,
            itemStyle: {
              color: s.return_1m >= 0 ? palette.upHex : palette.downHex,
              opacity: 0.85,
            },
          })),
          label: {
            show: true,
            formatter: (params: any) => {
              const v = Number(params?.value ?? 0);
              return `${v.toFixed(2)}%`;
            },
            fontSize: 11,
            color: palette.textPrimary,
            position: 'right',
          },
        },
      ],
    };
  }, [sectors, palette]);

  /** Heatmap: rows = sectors, cols = [1w, 1m, 3m, 6m, 1y], colour = return. */
  const heatmapOption: EChartsOption = useMemo(() => {
    const ordered = [...sectors].sort((a, b) => b.return_1m - a.return_1m);
    const data: [number, number, number][] = [];
    ordered.forEach((s, rowIdx) => {
      SECTOR_RETURN_PERIODS.forEach((period, colIdx) => {
        const key = PERIOD_RETURN_KEY[period];
        const v = Number(s[key] ?? 0);
        data.push([colIdx, rowIdx, Number(v.toFixed(2))]);
      });
    });
    return {
      tooltip: {
        position: 'top',
        formatter: (p: any) => {
          const [c, r, v] = p.value as [number, number, number];
          const sector = ordered[r]?.sector ?? '';
          const period = SECTOR_RETURN_LABELS[SECTOR_RETURN_PERIODS[c]];
          return `${sector} · ${period}<br/><b>${v >= 0 ? '+' : ''}${v.toFixed(2)}%</b>`;
        },
      },
      grid: { left: 150, right: 30, top: 32, bottom: 50 },
      xAxis: {
        type: 'category',
        data: SECTOR_RETURN_PERIODS.map((p) => SECTOR_RETURN_LABELS[p]),
        splitArea: { show: true },
        axisLabel: { color: palette.textPrimary, fontSize: 12 },
      },
      yAxis: {
        type: 'category',
        data: ordered.map((s) => s.sector),
        splitArea: { show: true },
        axisLabel: { color: palette.textPrimary, fontSize: 12 },
      },
      visualMap: {
        min: -6,
        max: 6,
        calculable: true,
        orient: 'horizontal',
        left: 'center',
        bottom: 6,
        text: ['+6%', '-6%'],
        textStyle: { color: palette.textSecondary, fontSize: 11 },
        inRange: { color: [palette.downHex, '#f4f4f0', palette.upHex] },
        itemWidth: 12,
        itemHeight: 80,
      },
      series: [
        {
          type: 'heatmap',
          data,
          label: {
            show: true,
            formatter: (p: any) => {
              const v = p.value[2] as number;
              return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
            },
            fontSize: 11,
            color: palette.textPrimary,
          },
          itemStyle: {
            borderColor: palette.border,
            borderWidth: 1,
          },
        },
      ],
    };
  }, [sectors, palette]);

  /** Relative-strength bar — quick view of who is beating the market. */
  const rsOption: EChartsOption = useMemo(() => {
    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
      },
      grid: { left: 130, right: 32, top: 20, bottom: 32 },
      xAxis: {
        type: 'value',
        name: '相对强弱',
        nameTextStyle: { color: palette.textSecondary, padding: [0, 0, 0, -40] },
        axisLabel: { color: palette.textSecondary },
        splitLine: { lineStyle: { color: palette.border } },
      },
      yAxis: {
        type: 'category',
        data: [...sectors].reverse().map((s) => s.sector),
        axisLabel: { color: palette.textPrimary, fontSize: 11 },
      },
      series: [
        {
          type: 'bar',
          data: [...sectors].reverse().map((s) => ({
            value: Number(s.relative_strength_1m.toFixed(2)),
            itemStyle: {
              color:
                s.relative_strength_1m >= 1 ? palette.upHex : palette.downHex,
              opacity: 0.85,
            },
          })),
          label: {
            show: true,
            formatter: (params: any) => Number(params?.value ?? 0).toFixed(2),
            fontSize: 11,
            color: palette.textPrimary,
            position: 'right',
          },
          markLine: {
            symbol: 'none',
            data: [
              {
                xAxis: 1,
                label: {
                  formatter: '市场平均 = 1.0',
                  color: palette.textSecondary,
                },
                lineStyle: {
                  color: palette.textSecondary,
                  type: 'dashed',
                },
              },
            ],
          },
        },
      ],
    };
  }, [sectors, palette]);

  // ------------------ Table ------------------

  const columns = [
    {
      title: <HelpPopover termKey="momentum_rank" mode={mode}>排名</HelpPopover>,
      dataIndex: 'momentum_rank',
      width: 60,
      render: (v: number) => (
        <span className="font-mono ad-table-accent">{v}</span>
      ),
    },
    {
      title: `行业板块 (${clsLabel})`,
      dataIndex: 'sector',
      width: 200,
      render: (v: string, r: SectorPerformance) => (
        <div className="ad-stack-xs">
          <span className="ad-table-text-primary">{v}</span>
          <span className="ad-table-text-secondary">
            {r.stock_count} 只个股 / {r.etf_count} 只 ETF
          </span>
        </div>
      ),
    },
    {
      title: <HelpPopover termKey="return_1w" mode={mode}>1周</HelpPopover>,
      dataIndex: 'return_1w',
      width: 90,
      render: (v: number) => <ReturnTag value={v} />,
    },
    {
      title: <HelpPopover termKey="return_1m" mode={mode}>1月</HelpPopover>,
      dataIndex: 'return_1m',
      width: 90,
      render: (v: number) => <ReturnTag value={v} />,
    },
    {
      title: <HelpPopover termKey="return_3m" mode={mode}>3月</HelpPopover>,
      dataIndex: 'return_3m',
      width: 90,
      render: (v: number) => <ReturnTag value={v} />,
    },
    {
      title: <HelpPopover termKey="return_6m" mode={mode}>6月</HelpPopover>,
      dataIndex: 'return_6m',
      width: 90,
      render: (v: number) => <ReturnTag value={v} />,
    },
    {
      title: <HelpPopover termKey="return_1y" mode={mode}>1年</HelpPopover>,
      dataIndex: 'return_1y',
      width: 90,
      render: (v: number) => <ReturnTag value={v} />,
    },
    {
      title: <HelpPopover termKey="sharpe_1y" mode={mode}>夏普</HelpPopover>,
      dataIndex: 'sharpe_1y',
      width: 80,
      render: (v: number) => (
        <span className="font-mono ad-table-mono">{v.toFixed(2)}</span>
      ),
    },
    {
      title: <HelpPopover termKey="rsi14" mode={mode}>RSI</HelpPopover>,
      dataIndex: 'rsi14',
      width: 70,
      render: (v: number) => (
        <span className="font-mono ad-table-mono">{v.toFixed(0)}</span>
      ),
    },
    {
      title: <HelpPopover termKey="relative_strength" mode={mode}>相对强弱</HelpPopover>,
      dataIndex: 'relative_strength_1m',
      width: 110,
      render: (v: number) => {
        let variant: 'rise' | 'fall' | 'neutral' = 'neutral';
        if (v > 1) variant = 'rise';
        if (v < 1) variant = 'fall';
        return <ThemeTag variant={variant}>{v.toFixed(2)}</ThemeTag>;
      },
    },
  ];

  // ------------------ Render ------------------

  const showSkeleton = isLoading && !data;
  const totalInstruments = sectors.reduce((sum, s) => sum + s.count, 0);
  const stockCount = sectors.reduce((sum, s) => sum + s.stock_count, 0);
  const etfCount = sectors.reduce((sum, s) => sum + s.etf_count, 0);

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="行业研究"
        title="行业板块轮动"
        description={`基于${clsLabel}行业分类的 A 股板块表现跟踪，相对强弱与轮动信号`}
        tutorial={
          <span>
            按行业板块（{clsLabel}）查看 A 股个股 + ETF 的整体表现：左侧是动量排名，中间是各周期收益热力图，右下角是相对强弱。出现「轮动信号」说明该板块排名一周内上升或下降 ≥3 位。
          </span>
        }
        extra={
          <div className="ad-cluster sector-rotation__header-extra">
            <Segmented<SectorClassification>
              size="small"
              value={classification}
              onChange={(v) => setClassification(v)}
              options={[
                { label: 'GICS', value: 'GICS' },
                { label: '申万一级', value: 'SW' },
              ]}
            />
            <LastUpdated
              at={dataUpdatedAt}
              loading={isFetching && !data}
            />
          </div>
        }
      />

      {/* Scope banner: clearly state what is and isn't included. */}
      <Panel variant="minimal" padding="sm" className="ad-mb-4">
        <div className="ad-info-banner">
          <InfoCircleOutlined className="ad-info-banner__icon" />
          <div className="ad-info-banner__body">
            <span className="ad-info-banner__title">当前范围</span>
            <span className="ad-info-banner__text">
              仅纳入 A 股（沪深北）<b>个股 + ETF</b>，分类体系为
              <Tag color={classification === 'SW' ? 'gold' : 'default'} className="sector-rotation__scope-tag">
                {classification === 'SW' ? '申万一级行业' : 'GICS 行业'}
              </Tag>
              数字币 / 美股 / 港股 不参与本轮动分析。
              {scope?.classification === 'SW' ? (
                <span className="sector-rotation__scope-source">
                  分类来源：<code className="font-mono">etf_info.sw_l1</code>
                  （个股由 Tushare 申万成分 / CSRC→申万 映射，ETF 由 sub_category/underlying_index 启发式匹配）。
                </span>
              ) : (
                scope?.classification && (
                  <span className="sector-rotation__scope-source">
                    分类来源：<code className="font-mono">etf_info.sector</code>
                    （个股由 CSRC→GICS 映射，ETF 由 sub_category/underlying_index 启发式匹配）。
                  </span>
                )
              )}
            </span>
          </div>
        </div>
      </Panel>

      {/* Headline metrics */}
      <div className="ad-metric-strip ad-metric-strip--cols-4 ad-mb-5">
        <div className="ad-metric-item">
          <div className="ad-metric-item__label">分析日期</div>
          <div className="ad-metric-item__value">{data?.trade_date || '—'}</div>
        </div>
        <div className="ad-metric-item">
          <div className="ad-metric-item__label">市场平均 1月</div>
          <div
            className="ad-metric-item__value ad-metric-item__value--colored"
            style={{ color: getReturnColor(marketAvg?.return_1m ?? 0) }}
          >
            {(marketAvg?.return_1m ?? 0).toFixed(2)}
            <span className="ad-metric-item__suffix">%</span>
          </div>
        </div>
        <div className="ad-metric-item">
          <div className="ad-metric-item__label">行业板块数</div>
          <div className="ad-metric-item__value">{sectors.length}</div>
        </div>
        <div className="ad-metric-item">
          <div className="ad-metric-item__label">纳入标的</div>
          <div className="ad-metric-item__value">
            {totalInstruments}
            <span className="ad-metric-item__suffix">
              {' '}
              ({stockCount}股 / {etfCount}基)
            </span>
          </div>
        </div>
      </div>

      {/* Rotation signals */}
      {signals.length > 0 && (
        <Panel
          title={<HelpPopover termKey="rotation_signal" mode={mode}>轮动信号</HelpPopover>}
          variant="default"
          className="ad-mb-4"
        >
          <div className="ad-stack-full">
            {signals.map((signal, idx) => (
              <Alert
                key={`${signal.sector}-${idx}`}
                message={signal.message}
                description={
                  <span className="ad-table-text-secondary">
                    上周排名 #{signal.previous_rank} → 本周 #{signal.current_rank}
                    （变动 {signal.rank_change > 0 ? '+' : ''}{signal.rank_change} 位）
                  </span>
                }
                type={signal.type === 'up' ? 'success' : 'warning'}
                showIcon
              />
            ))}
          </div>
        </Panel>
      )}

      {/* Charts row 1 — ranking + relative strength */}
      <div className="ad-mb-4">
        <ResponsiveGrid cols={2} gap="md">
          <Panel
            title="行业板块 1月收益排名"
            extra={
              <span className="ad-table-text-secondary sector-rotation__chart-hint">
                按 1月平均收益降序
              </span>
            }
            variant="default"
          >
            {showSkeleton ? (
              <Spin />
            ) : sectors.length === 0 ? (
              <EmptyState
                title="暂无板块数据"
                description={`当前 A 股范围内无${clsLabel}板块数据，请稍后重试或检查 ETL。`}
              />
            ) : (
              <div className="ad-chart-container">
                <ReactECharts option={rankOption} />
              </div>
            )}
          </Panel>
          <Panel
            title="行业相对强弱 (vs 市场平均)"
            extra={
              <span className="ad-table-text-secondary sector-rotation__chart-hint">
                1月相对强弱 = 板块收益 / 市场平均
              </span>
            }
            variant="default"
          >
            {showSkeleton ? (
              <Spin />
            ) : sectors.length === 0 ? (
              <EmptyState
                title="暂无板块数据"
                description={`当前 A 股范围内无${clsLabel}板块数据。`}
              />
            ) : (
              <div className="ad-chart-container">
                <ReactECharts option={rsOption} />
              </div>
            )}
          </Panel>
        </ResponsiveGrid>
      </div>

      {/* Heatmap — multi-period returns by sector */}
      <div className="ad-mb-4">
        <Panel
          title="多周期收益热力图"
          extra={
            <span className="ad-table-text-secondary sector-rotation__chart-hint">
              行：{clsLabel}板块 · 列：收益周期 · 色：涨跌强度
            </span>
          }
          variant="default"
        >
          {showSkeleton ? (
            <Spin />
          ) : sectors.length === 0 ? (
            <EmptyState
              title="暂无板块数据"
              description={`当前 A 股范围内无${clsLabel}板块数据。`}
            />
          ) : (
            <div className="ad-chart-container sector-rotation__heatmap-container">
              <ReactECharts option={heatmapOption} />
            </div>
          )}
        </Panel>
      </div>

      {/* Detail panel — split into 板块汇总 + 成份股构成 tabs */}
      <Panel
        title="行业板块详细数据"
        variant="default"
        padding="none"
      >
        <Tabs
          className="ad-px-4"
          activeKey={detailTab}
          onChange={(k) => setDetailTab(k as DetailTab)}
          items={[
            { key: 'summary', label: '板块汇总' },
            { key: 'constituents', label: '成份股构成' },
          ]}
        />
        {detailTab === 'summary' ? (
          <div className="ad-table-scroll ad-table-sticky ad-px-4 ad-pb-4">
            <Table
              dataSource={sectors}
              columns={columns}
              rowKey="sector"
              size="small"
              pagination={false}
              loading={isLoading}
            />
          </div>
        ) : (
          <ConstituentsTab
            defaultSector={
              sectors[0]?.sector ?? sectorsData?.items?.[0]?.sector ?? null
            }
            sectors={sectorsData?.items ?? []}
            classification={classification}
          />
        )}
      </Panel>
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Constituents tab — top-N instruments inside a selected sector (STOCK + ETF).
// ---------------------------------------------------------------------------

function ConstituentsTab({
  defaultSector,
  sectors,
  classification,
}: {
  defaultSector: string | null;
  sectors: { sector: string; stock_count: number; etf_count: number }[];
  classification: SectorClassification;
}) {
  const [selectedSector, setSelectedSector] = useState<string | null>(
    defaultSector,
  );
  const [topN, setTopN] = useState<number>(20);

  // Re-sync when the upstream defaultSector changes (e.g. data reload) or
  // when the taxonomy switches and the selected sector no longer exists in
  // the new list (GICS names differ from 申万 names).
  useEffect(() => {
    if (
      sectors.length > 0 &&
      selectedSector &&
      !sectors.some((s) => s.sector === selectedSector)
    ) {
      setSelectedSector(defaultSector);
    } else if (defaultSector && !selectedSector) {
      setSelectedSector(defaultSector);
    }
  }, [defaultSector, selectedSector, sectors]);

  const { data, isLoading, isFetching } = useSectorConstituents(
    selectedSector,
    topN,
    undefined,
    classification,
  );

  const items = data?.items ?? [];
  const sectorMeta = sectors.find((s) => s.sector === selectedSector);

  const constituentsColumns = useMemo(
    () => [
      {
        title: '代码',
        dataIndex: 'code',
        width: 110,
        render: (v: string) => <span className="font-mono ad-table-accent">{v}</span>,
      },
      {
        title: '名称',
        dataIndex: 'name',
        width: 180,
        render: (v: string) => (
          <div className="ad-stack-xs">
            <span className="ad-table-text-primary">{v}</span>
            {sectorMeta && (
              <span className="ad-table-text-secondary">
                {sectorMeta.stock_count}股 / {sectorMeta.etf_count}基
              </span>
            )}
          </div>
        ),
      },
      {
        title: '类型',
        dataIndex: 'instrument_type',
        width: 80,
        render: (v: SectorConstituent['instrument_type']) =>
          v === 'STOCK' ? (
            <Tag color="blue">个股</Tag>
          ) : (
            <Tag color="purple">ETF</Tag>
          ),
      },
      {
        title: (
          <span>
            权重 (元)
            <span className="ad-table-text-secondary sector-rotation__weight-label">
              {items[0]?.weight_label === '规模' ? '· 规模' : '· 市值'}
            </span>
          </span>
        ),
        dataIndex: 'weight',
        width: 150,
        align: 'right' as const,
        sorter: (a: SectorConstituent, b: SectorConstituent) =>
          (a.weight ?? -Infinity) - (b.weight ?? -Infinity),
        render: (v: number | null) =>
          v == null ? (
            <span className="ad-table-text-secondary">—</span>
          ) : (
            <span className="font-mono ad-table-mono">{formatWeight(v)}</span>
          ),
      },
      {
        title: '1周',
        dataIndex: 'return_1w',
        width: 80,
        render: (v: number | null) =>
          v == null ? <span className="ad-table-text-secondary">—</span> : <ReturnTag value={v} />,
      },
      {
        title: '1月',
        dataIndex: 'return_1m',
        width: 80,
        render: (v: number | null) =>
          v == null ? <span className="ad-table-text-secondary">—</span> : <ReturnTag value={v} />,
      },
      {
        title: '3月',
        dataIndex: 'return_3m',
        width: 80,
        render: (v: number | null) =>
          v == null ? <span className="ad-table-text-secondary">—</span> : <ReturnTag value={v} />,
      },
      {
        title: '6月',
        dataIndex: 'return_6m',
        width: 80,
        render: (v: number | null) =>
          v == null ? <span className="ad-table-text-secondary">—</span> : <ReturnTag value={v} />,
      },
      {
        title: '1年',
        dataIndex: 'return_1y',
        width: 80,
        render: (v: number | null) =>
          v == null ? <span className="ad-table-text-secondary">—</span> : <ReturnTag value={v} />,
      },
      {
        title: '夏普',
        dataIndex: 'sharpe_1y',
        width: 70,
        render: (v: number | null) =>
          v == null ? (
            <span className="ad-table-text-secondary">—</span>
          ) : (
            <span className="font-mono ad-table-mono">{v.toFixed(2)}</span>
          ),
      },
      {
        title: 'RSI',
        dataIndex: 'rsi14',
        width: 60,
        render: (v: number | null) =>
          v == null ? (
            <span className="ad-table-text-secondary">—</span>
          ) : (
            <span className="font-mono ad-table-mono">{v.toFixed(0)}</span>
          ),
      },
    ],
    [items, sectorMeta],
  );

  return (
    <div className="ad-px-4 ad-pb-4 ad-pt-2">
      {/* Filter strip */}
      <div className="ad-stack-row ad-mb-3 sector-rotation__filter-bar">
        <div className="ad-stack-row sector-rotation__filter-group">
          <span className="ad-table-text-secondary sector-rotation__filter-label">板块</span>
          <Select
            value={selectedSector ?? undefined}
            onChange={(v) => setSelectedSector(v)}
            className="sector-rotation__sector-select"
            placeholder={`选择${classification === 'SW' ? '申万一级' : 'GICS'}板块`}
            options={sectors.map((s) => ({
              label: `${s.sector} (${s.stock_count}股 / ${s.etf_count}基)`,
              value: s.sector,
            }))}
            showSearch
            optionFilterProp="label"
          />
        </div>
        <div className="ad-stack-row sector-rotation__filter-group">
          <span className="ad-table-text-secondary sector-rotation__filter-label">TOP</span>
          <Select
            value={topN}
            onChange={(v) => setTopN(v)}
            className="sector-rotation__topn-select"
            options={[
              { label: '10', value: 10 },
              { label: '20', value: 20 },
              { label: '50', value: 50 },
              { label: '100', value: 100 },
              { label: '200', value: 200 },
            ]}
          />
        </div>
        {data && (
          <span className="ad-table-text-secondary sector-rotation__filter-label">
            展示 {data.count} / {data.total_in_sector} （按 {items[0]?.weight_label ?? '权重'} 降序）
            {data.trade_date ? ` · 快照 ${data.trade_date}` : ''}
          </span>
        )}
      </div>

      {isLoading && !data ? (
        <Spin />
      ) : !selectedSector ? (
        <EmptyState
          title="请选择板块"
          description={`从上方下拉框选择要查看的${classification === 'SW' ? '申万一级' : 'GICS'}板块。`}
        />
      ) : items.length === 0 ? (
        <EmptyState
          title="暂无成份股"
          description={
            data?.total_in_sector === 0
              ? `板块 ${selectedSector} 当前没有任何 ETF/个股。`
              : `板块 ${selectedSector} 没有可显示的成份股（可能尚未刷新指标）。`
          }
        />
      ) : (
        <div className="ad-table-scroll ad-table-sticky">
          <Table
            dataSource={items.map((i) => ({ ...i, key: i.code }))}
            columns={constituentsColumns}
            rowKey="code"
            size="small"
            pagination={false}
            loading={isFetching && !!data}
          />
        </div>
      )}
    </div>
  );
}

/** Format a CNY 元 weight (e.g. 2_500_000_000 → "25.00亿"). */
function formatWeight(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e8) return `${(value / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(value / 1e4).toFixed(2)}万`;
  return value.toFixed(0);
}