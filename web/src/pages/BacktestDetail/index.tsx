import { useParams } from 'react-router-dom';
import { Statistic, Table, Spin, Tabs } from 'antd';
import Panel from '@/components/Panel';
import HelpTrigger from '@/components/HelpTrigger';
import HelpPopover from '@/components/HelpPopover';
import { useBacktestDetail } from '@/hooks/useBacktests';
import { useAttribution } from '@/hooks/useAttribution';
import { useAIHelp } from '@/hooks/useAIHelp';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { buildBacktestDetailContext } from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';
import type { AttributionEffect } from '@/types/backtest';

export default function BacktestDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading } = useBacktestDetail(id || '');
  const { data: attribution, isLoading: attributionLoading } = useAttribution(id || '');
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
      lineStyle: { color: 'var(--accent)', width: 2 },
      itemStyle: { color: 'var(--accent)' },
      areaStyle: { color: 'var(--accent-dim)' },
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
      render: (v: number) => <span style={{ color: v >= 0 ? 'var(--color-rise)' : 'var(--color-fall)' }}>{v}%</span>,
    },
  ];

  const attributionColumns = [
    { title: '板块/资产', dataIndex: 'sector', render: (v?: string) => v || '-' },
    {
      title: '配置效应',
      dataIndex: 'allocation',
      render: (v?: number) => (v != null ? `${v >= 0 ? '+' : ''}${v.toFixed(2)}%` : '-'),
    },
    {
      title: '选股效应',
      dataIndex: 'selection',
      render: (v?: number) => (v != null ? `${v >= 0 ? '+' : ''}${v.toFixed(2)}%` : '-'),
    },
    {
      title: '交互效应',
      dataIndex: 'interaction',
      render: (v?: number) => (v != null ? `${v >= 0 ? '+' : ''}${v.toFixed(2)}%` : '-'),
    },
    {
      title: '合计',
      dataIndex: 'total',
      render: (v?: number) => (v != null ? `${v >= 0 ? '+' : ''}${v.toFixed(2)}%` : '-'),
    },
  ];

  const gridStyle = {
    display: 'grid',
    gridTemplateColumns: isMobile ? 'repeat(2, 1fr)' : 'repeat(3, 1fr)',
    borderTop: '1px solid var(--border-default)',
  };

  const cellStyle = (idx: number) => ({
    padding: 'var(--space-4)',
    borderBottom: '1px solid var(--border-default)',
    borderRight: (idx + 1) % (isMobile ? 2 : 3) !== 0 ? '1px solid var(--border-default)' : 'none',
  });

  const overviewTab = (
    <div>
      <Panel title={`回测详情 #${data.id}`} padding="md" style={{ marginBottom: 'var(--space-5)' }} extra={<HelpTrigger tooltip="AI 解释回测指标" onClick={handleOpenHelp} />}>
        <div style={{ ...gridStyle, borderTop: 'none' }}>
          {[
            { title: <HelpPopover termKey="total_return">总收益</HelpPopover>, value: metrics.total_return, suffix: '%' },
            { title: <HelpPopover termKey="annualized_return">年化收益</HelpPopover>, value: metrics.annualized_return, suffix: '%' },
            { title: <HelpPopover termKey="max_drawdown_1y">最大回撤</HelpPopover>, value: metrics.max_drawdown, suffix: '%' },
            { title: <HelpPopover termKey="sharpe_ratio">夏普比率</HelpPopover>, value: metrics.sharpe_ratio },
            { title: <HelpPopover termKey="win_rate">胜率</HelpPopover>, value: metrics.win_rate, suffix: '%' },
            { title: <HelpPopover termKey="trade_count">交易次数</HelpPopover>, value: metrics.trade_count, precision: undefined },
          ].map((m, idx) => (
            <div key={idx} style={cellStyle(idx)}>
              <Statistic title={m.title} value={m.value} suffix={m.suffix} precision={m.precision !== undefined ? m.precision : 2} />
            </div>
          ))}
        </div>
      </Panel>

      <Panel title={<HelpPopover termKey="nav_curve">净值曲线</HelpPopover>} padding="md" style={{ marginBottom: 'var(--space-5)' }}>
        <ReactECharts option={navOption} style={{ height: isMobile ? 250 : 320 }} />
      </Panel>
    </div>
  );

  const attributionTab = (
    <div>
      <Panel title="归因概览" padding="md" style={{ marginBottom: 'var(--space-5)' }}>
        <div style={gridStyle}>
          {[
            { title: '策略收益', value: attribution?.total_return, suffix: '%' },
            { title: '基准收益', value: attribution?.benchmark_return, suffix: '%' },
            { title: '超额收益', value: attribution?.excess_return, suffix: '%' },
            { title: '配置贡献', value: attribution?.summary?.allocation_pct, suffix: '%' },
            { title: '选股贡献', value: attribution?.summary?.selection_pct, suffix: '%' },
            { title: '交互贡献', value: attribution?.summary?.interaction_pct, suffix: '%' },
          ].map((m, idx) => (
            <div key={m.title} style={cellStyle(idx)}>
              <Statistic title={m.title} value={m.value} suffix={m.suffix} precision={2} />
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="归因明细" padding="md" style={{ marginBottom: 'var(--space-5)' }}>
        {attributionLoading ? (
          <Spin />
        ) : (
          <Table
            dataSource={(attribution?.effects || []).map((e: AttributionEffect, i: number) => ({ ...e, key: e.sector || `${i}` }))}
            columns={attributionColumns}
            rowKey="key"
            size="small"
            scroll={{ x: 'max-content' }}
            pagination={{ pageSize: 10 }}
          />
        )}
      </Panel>

      <Panel title="交易统计" padding="md" style={{ marginBottom: 'var(--space-5)' }}>
        <div style={gridStyle}>
          {[
            { title: '总交易次数', value: attribution?.trade_stats?.total_trades, suffix: undefined },
            { title: '盈利次数', value: attribution?.trade_stats?.winning_trades, suffix: undefined },
            { title: '亏损次数', value: attribution?.trade_stats?.losing_trades, suffix: undefined },
            { title: '胜率', value: attribution?.trade_stats?.win_rate, suffix: '%' },
            { title: '平均收益', value: attribution?.trade_stats?.avg_return, suffix: '%' },
          ].map((m, idx) => (
            <div key={m.title} style={cellStyle(idx)}>
              <Statistic title={m.title} value={m.value} suffix={m.suffix} precision={m.suffix === '%' ? 2 : 0} />
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );

  const tradesTab = (
    <Panel title={<HelpPopover termKey="trade_record">交易记录</HelpPopover>} padding="md">
      <Table
        dataSource={data.trades || []}
        columns={tradeColumns}
        rowKey={(r: any) => `${r.entry_date}-${r.entry_price}`}
        size="small"
        scroll={{ x: 'max-content' }}
        pagination={{ pageSize: 10 }}
      />
    </Panel>
  );

  const tabItems = [
    { key: 'overview', label: '概览', children: overviewTab },
    { key: 'attribution', label: '绩效归因', children: attributionTab },
    { key: 'trades', label: '交易记录', children: tradesTab },
  ];

  return <Tabs items={tabItems} defaultActiveKey="overview" />;
}
