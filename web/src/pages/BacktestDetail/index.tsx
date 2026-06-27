import { useParams } from 'react-router-dom';
import { Statistic, Table, Spin } from 'antd';
import Panel from '@/components/Panel';
import HelpTrigger from '@/components/HelpTrigger';
import HelpPopover from '@/components/HelpPopover';
import { useBacktestDetail } from '@/hooks/useBacktests';
import { useAIHelp } from '@/hooks/useAIHelp';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { buildBacktestDetailContext } from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';

export default function BacktestDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading } = useBacktestDetail(id || '');
  const { open } = useAIHelp();
  const isMobile = useIsMobile();

  if (isLoading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (!data) return <div>回测未找到</div>;

  const metrics = data.metrics || {};

  const handleOpenHelp = () => {
    open({
      pageType: 'backtest_detail',
      pageTitle: '回测详情',
      contextData: buildBacktestDetailContext(data),
      quickQuestions: getQuickQuestions('backtest_detail'),
    });
  };

  const navData = data.daily_nav || [];
  const navOption: EChartsOption = {
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 30, bottom: 30 },
    xAxis: { type: 'category', data: navData.map((d: any) => d.date), axisLine: { lineStyle: { color: 'var(--text-tertiary)' } } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: 'var(--border-default)' } } },
    series: [{
      type: 'line',
      data: navData.map((d: any) => d.nav),
      smooth: true,
      lineStyle: { color: '#22d3ee', width: 2 },
      itemStyle: { color: '#22d3ee' },
      areaStyle: { color: 'rgba(34,211,238,0.08)' },
    }],
  };

  const tradeColumns = [
    { title: '入场日期', dataIndex: 'entry_date' },
    { title: '出场日期', dataIndex: 'exit_date' },
    { title: '入场价', dataIndex: 'entry_price' },
    { title: '出场价', dataIndex: 'exit_price' },
    {
      title: '收益',
      dataIndex: 'pnl_pct',
      render: (v: number) => <span style={{ color: v >= 0 ? '#ef4444' : '#22c55e' }}>{v}%</span>,
    },
  ];

  return (
    <div>
      <Panel title={`回测详情 #${data.id}`} padding="md" style={{ marginBottom: 'var(--space-5)' }} extra={<HelpTrigger tooltip="AI 解释回测指标" onClick={handleOpenHelp} />}>
        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? 'repeat(2, 1fr)' : 'repeat(3, 1fr)', gap: 0, borderTop: '1px solid var(--border-default)' }}>
          {[
            { title: <HelpPopover termKey="total_return">总收益</HelpPopover>, value: metrics.total_return, suffix: '%' },
            { title: <HelpPopover termKey="annualized_return">年化收益</HelpPopover>, value: metrics.annualized_return, suffix: '%' },
            { title: <HelpPopover termKey="max_drawdown_1y">最大回撤</HelpPopover>, value: metrics.max_drawdown, suffix: '%' },
            { title: <HelpPopover termKey="sharpe_ratio">夏普比率</HelpPopover>, value: metrics.sharpe_ratio },
            { title: <HelpPopover termKey="win_rate">胜率</HelpPopover>, value: metrics.win_rate, suffix: '%' },
            { title: <HelpPopover termKey="trade_count">交易次数</HelpPopover>, value: metrics.trade_count, precision: undefined },
          ].map((m, idx) => (
            <div
              key={idx}
              style={{
                padding: 'var(--space-4)',
                borderBottom: '1px solid var(--border-default)',
                borderRight: (idx + 1) % (isMobile ? 2 : 3) !== 0 ? '1px solid var(--border-default)' : 'none',
              }}
            >
              <Statistic title={m.title} value={m.value} suffix={m.suffix} precision={m.precision !== undefined ? m.precision : 2} />
            </div>
          ))}
        </div>
      </Panel>

      <Panel title={<HelpPopover termKey="nav_curve">净值曲线</HelpPopover>} padding="md" style={{ marginBottom: 'var(--space-5)' }}>
        <ReactECharts option={navOption} style={{ height: isMobile ? 250 : 320 }} />
      </Panel>

      <Panel title={<HelpPopover termKey="trade_record">交易记录</HelpPopover>} padding="md" style={{ marginBottom: 'var(--space-5)' }}>
        <Table
          dataSource={data.trades || []}
          columns={tradeColumns}
          rowKey={(r: any) => `${r.entry_date}-${r.entry_price}`}
          size="small"
          scroll={{ x: 'max-content' }}
          pagination={{ pageSize: 10 }}
        />
      </Panel>
    </div>
  );
}
