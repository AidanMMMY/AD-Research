import { useEffect, useMemo, useState } from 'react';
import { Alert, Spin, Table, Tag } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useSectorRotation } from '@/hooks/useSectorRotation';
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
  SectorPerformance,
  SectorReturnPeriod,
} from '@/types/sector_rotation';
import { SECTOR_RETURN_LABELS, SECTOR_RETURN_PERIODS } from '@/types/sector_rotation';

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

export default function SectorRotation() {
  const mode = useSettingsStore((s) => s.mode);
  const { data, isLoading, isFetching, dataUpdatedAt } = useSectorRotation();
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
      title: '行业板块 (GICS)',
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
        description="基于 GICS 行业分类的 A 股板块表现跟踪，相对强弱与轮动信号"
        tutorial={
          <span>
            按行业板块（GICS 一级）查看 A 股个股 + ETF 的整体表现：左侧是动量排名，中间是各周期收益热力图，右下角是相对强弱。出现「轮动信号」说明该板块排名一周内上升或下降 ≥3 位。
          </span>
        }
        extra={
          <LastUpdated
            at={dataUpdatedAt}
            loading={isFetching && !data}
          />
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
              <Tag color="default" style={{ marginLeft: 6, marginRight: 6 }}>GICS 行业</Tag>
              数字币 / 美股 / 港股 不参与本轮动分析。
              {scope?.classification && (
                <span style={{ marginLeft: 8 }}>
                  分类来源：<code className="font-mono">etf_info.sector</code>
                  （个股由 CSRC→GICS 映射，ETF 由 sub_category/underlying_index 启发式匹配）。
                </span>
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
              <span className="ad-table-text-secondary" style={{ fontSize: 12 }}>
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
                description="当前 A 股范围内无 GICS 板块数据，请稍后重试或检查 ETL。"
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
              <span className="ad-table-text-secondary" style={{ fontSize: 12 }}>
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
                description="当前 A 股范围内无 GICS 板块数据。"
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
            <span className="ad-table-text-secondary" style={{ fontSize: 12 }}>
              行：GICS 板块 · 列：收益周期 · 色：涨跌强度
            </span>
          }
          variant="default"
        >
          {showSkeleton ? (
            <Spin />
          ) : sectors.length === 0 ? (
            <EmptyState
              title="暂无板块数据"
              description="当前 A 股范围内无 GICS 板块数据。"
            />
          ) : (
            <div className="ad-chart-container" style={{ minHeight: 420 }}>
              <ReactECharts option={heatmapOption} />
            </div>
          )}
        </Panel>
      </div>

      {/* Detail table */}
      <Panel title="行业板块详细数据" variant="default">
        <div className="ad-density-dense ad-table-scroll ad-table-sticky">
          <Table
            dataSource={sectors}
            columns={columns}
            rowKey="sector"
            size="small"
            pagination={false}
            loading={isLoading}
          />
        </div>
      </Panel>
    </PageShell>
  );
}