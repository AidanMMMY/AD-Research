import { useMemo } from 'react';
import { Table, Spin, Alert, Space } from 'antd';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useSectorRotation } from '@/hooks/useSectorRotation';
import { useSparkline } from '@/hooks/useSparkline';
import ReturnTag from '@/components/ReturnTag';
import ThemeTag from '@/components/ThemeTag';
import Sparkline from '@/components/Sparkline';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import HelpPopover from '@/components/HelpPopover';
import { getReturnColor, getUpColor, getDownColor } from '@/utils/color';

/**
 * Sparkline cell. Each sector row doesn't carry a per-instrument code,
 * so the inline mock remains the visible behavior for now. The hook is
 * imported and called (with a stable key) so a future per-sector series
 * can plug in without restructuring the columns.
 */
function SectorSparklineCell({ record }: { record: any }) {
  // Sectors have no code — pass a sentinel so the hook stays disabled.
  // When a sector-aggregate endpoint lands, swap ``null`` for a category
  // key and turn the hook on.
  useSparkline({ code: null, enabled: false });
  const base = 100 + (record.return_1m || 0);
  const seed = (record.momentum_rank || 1) * 7;
  const out: number[] = [];
  let v = 100;
  for (let i = 0; i < 30; i++) {
    const r = (((i + seed) * 13) % 11 - 5) / 10;
    v += r;
    out.push(base + (v - 100) * 0.3);
  }
  return <Sparkline data={out} width={80} height={20} />;
}

export default function SectorRotation() {
  const { data, isLoading } = useSectorRotation();

  const sectors = data?.sectors || [];
  const signals = data?.rotation_signals || [];
  const marketAvg = data?.market_avg;

  const barOption: EChartsOption = useMemo(() => {
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 80, right: 20, top: 20, bottom: 30 },
      xAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
      yAxis: {
        type: 'category',
        data: [...sectors].reverse().map((s) => s.category),
        axisLabel: { fontSize: 11 },
      },
      series: [
        {
          type: 'bar',
          data: [...sectors].reverse().map((s) => ({
            value: s.return_1m,
            itemStyle: { color: s.return_1m >= 0 ? getUpColor() : getDownColor() },
          })),
          label: { show: true, formatter: '{c}%', fontSize: 10 },
        },
      ],
    };
  }, [sectors]);

  const rsOption: EChartsOption = useMemo(() => {
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 60, right: 20, top: 30, bottom: 60 },
      xAxis: {
        type: 'category',
        data: sectors.map((s) => s.category),
        axisLabel: { rotate: 45, fontSize: 10 },
      },
      yAxis: { type: 'value', name: '相对强弱' },
      series: [
        {
          type: 'bar',
          data: sectors.map((s) => ({
            value: s.relative_strength_1m,
            itemStyle: { color: s.relative_strength_1m >= 1 ? getUpColor() : getDownColor() },
          })),
          markLine: { data: [{ yAxis: 1, label: { formatter: '市场平均' } }] },
        },
      ],
    };
  }, [sectors]);

  const columns = [
    { title: <HelpPopover termKey="momentum_rank">排名</HelpPopover>, dataIndex: 'momentum_rank', width: 60 },
    { title: '板块', dataIndex: 'category' },
    { title: '标的数量', dataIndex: 'count', width: 80 },
    {
      title: <HelpPopover termKey="return_1m">1月收益</HelpPopover>,
      dataIndex: 'return_1m',
      render: (v: number) => <ReturnTag value={v} />,
      width: 100,
    },
    {
      title: <HelpPopover termKey="return_3m">3月收益</HelpPopover>,
      dataIndex: 'return_3m',
      render: (v: number) => <ReturnTag value={v} />,
      width: 100,
    },
    { title: <HelpPopover termKey="sharpe_1y">夏普</HelpPopover>, dataIndex: 'sharpe_1y', width: 80 },
    { title: <HelpPopover termKey="volatility_20d">波动率</HelpPopover>, dataIndex: 'volatility_20d', render: (v: number) => `${(v * 100).toFixed(1)}%`, width: 90 },
    { title: <HelpPopover termKey="rsi14">RSI</HelpPopover>, dataIndex: 'rsi14', width: 70 },
    {
      title: <HelpPopover termKey="relative_strength">相对强弱</HelpPopover>,
      dataIndex: 'relative_strength_1m',
      render: (v: number) => {
        let variant: 'rise' | 'fall' | 'neutral' = 'neutral';
        if (v > 1) variant = 'rise';
        if (v < 1) variant = 'fall';
        return <ThemeTag variant={variant}>{v.toFixed(2)}</ThemeTag>;
      },
      width: 100,
    },
    {
      title: '近 30 日',
      key: 'sparkline_30d',
      width: 100,
      render: (_: unknown, record: any) => <SectorSparklineCell record={record} />,
    },
  ];

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        title="板块轮动"
        description="分析各板块收益排名与相对强弱，跟踪轮动信号"
      />
      <div className="ad-metric-strip ad-mb-5">
        <div className="ad-metric-item">
          <div className="ad-metric-item__label">分析日期</div>
          <div className="ad-metric-item__value">{data?.trade_date || '—'}</div>
        </div>
        <div className="ad-metric-item">
          <div className="ad-metric-item__label">市场平均1月收益</div>
          <div
            className="ad-metric-item__value ad-metric-item__value--colored"
            style={{ color: getReturnColor(marketAvg?.return_1m ?? 0) }}
          >
            {(marketAvg?.return_1m ?? 0).toFixed(2)}
            <span className="ad-metric-item__suffix">%</span>
          </div>
        </div>
        <div className="ad-metric-item">
          <div className="ad-metric-item__label">板块数量</div>
          <div className="ad-metric-item__value">{sectors.length}</div>
        </div>
      </div>

      {signals.length > 0 && (
        <Panel title={<HelpPopover termKey="rotation_signal">轮动信号</HelpPopover>} variant="default" className="ad-mb-4">
          <Space direction="vertical" className="ad-stack-full">
            {signals.map((signal, idx) => (
              <Alert
                key={idx}
                message={signal.message}
                type={signal.type === 'up' ? 'success' : 'warning'}
                showIcon
              />
            ))}
          </Space>
        </Panel>
      )}

      <div className="ad-mb-4">
        <ResponsiveGrid cols={2} gap="md">
          <Panel title="板块1月收益排名" variant="default">
            {isLoading ? (
              <Spin />
            ) : (
              <div className="ad-chart-container">
                <ReactECharts option={barOption} />
              </div>
            )}
          </Panel>
          <Panel title="板块相对强弱（vs 市场平均）" variant="default">
            {isLoading ? (
              <Spin />
            ) : (
              <div className="ad-chart-container">
                <ReactECharts option={rsOption} />
              </div>
            )}
          </Panel>
        </ResponsiveGrid>
      </div>

      <Panel title="板块详细数据" variant="default">
        <div className="ad-density-dense ad-table-scroll ad-table-sticky">
          <Table
            dataSource={sectors}
            columns={columns}
            rowKey="category"
            size="small"
            pagination={false}
            loading={isLoading}
          />
        </div>
      </Panel>
    </PageShell>
  );
}
