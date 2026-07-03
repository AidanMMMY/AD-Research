import { useParams, useNavigate } from 'react-router-dom';
import { Statistic, Table, Spin, Tabs, Alert, Button } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined, ExperimentOutlined } from '@ant-design/icons';
import Panel from '@/components/Panel';
import PageHeader from '@/components/PageHeader';
import PageShell from '@/components/PageShell';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import StatCard from '@/components/StatCard';
import SectionHeading from '@/components/SectionHeading';
import HelpTrigger from '@/components/HelpTrigger';
import HelpPopover from '@/components/HelpPopover';
import { useBacktestDetail } from '@/hooks/useBacktests';
import { useAttribution } from '@/hooks/useAttribution';
import { useAIHelp } from '@/hooks/useAIHelp';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { buildBacktestDetailContext } from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';
import { formatDateTime } from '@/utils/datetime';
import type { AttributionEffect } from '@/types/backtest';

export default function BacktestDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data, isLoading, error } = useBacktestDetail(id || '');
  const { data: attribution, isLoading: attributionLoading } = useAttribution(id || '');
  const { open } = useAIHelp();

  if (isLoading) {
    return (
      <PageShell maxWidth="wide">
        <div role="status" aria-live="polite" className="empty-state detail-loading-wrapper">
          <Spin size="large" />
          <div className="detail-loading-message">
            正在加载回测结果…
          </div>
        </div>
      </PageShell>
    );
  }
  if (error) {
    return (
      <PageShell maxWidth="wide">
        <div className="detail-error">
          <Alert
            message="加载回测失败"
            description={(error as Error)?.message ?? '网络异常，请稍后重试'}
            type="error"
            showIcon
            action={
              <Button size="small" onClick={() => navigate('/backtests')}>
                返回回测列表
              </Button>
            }
          />
        </div>
      </PageShell>
    );
  }
  if (!data) {
    return (
      <PageShell maxWidth="wide">
        <div className="detail-error">
          <Alert
            message="回测不存在"
            description={`未找到 ID 为 ${id} 的回测记录，可能已被删除或尚未生成`}
            type="warning"
            showIcon
            action={
              <Button size="small" onClick={() => navigate('/backtests')}>
                返回回测列表
              </Button>
            }
          />
        </div>
      </PageShell>
    );
  }

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

  const formatSigned = (v?: number | null) => {
    if (v == null) return '—';
    return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`;
  };

  const kpiItems = [
    { label: '总收益', value: metrics.total_return, suffix: '%', color: metrics.total_return >= 0 ? 'detail-kpi-rise' : 'detail-kpi-fall' },
    { label: '夏普比率', value: metrics.sharpe_ratio, suffix: undefined, color: 'detail-kpi-accent' },
    { label: '最大回撤', value: metrics.max_drawdown, suffix: '%', color: 'detail-kpi-fall' },
    { label: '胜率', value: metrics.win_rate, suffix: '%', color: 'detail-kpi-accent' },
  ];

  const tradeColumns = [
    { title: '入场日期', dataIndex: 'entry_date' },
    { title: '出场日期', dataIndex: 'exit_date' },
    { title: '入场价', dataIndex: 'entry_price', render: (v: any) => <span className="tabular-nums">{v}</span> },
    { title: '出场价', dataIndex: 'exit_price', render: (v: any) => <span className="tabular-nums">{v}</span> },
    {
      title: '收益',
      dataIndex: 'pnl_pct',
      render: (v: number) => (
        <span
          className={`tabular-nums detail-return-cell ${v >= 0 ? 'detail-return-cell--rise' : 'detail-return-cell--fall'}`}
        >
          {v > 0 ? (
            <ArrowUpOutlined className="detail-arrow-icon" aria-label="up" />
          ) : v < 0 ? (
            <ArrowDownOutlined className="detail-arrow-icon" aria-label="down" />
          ) : null}
          {v}%
        </span>
      ),
    },
  ];

  const attributionColumns = [
    { title: '板块/资产', dataIndex: 'sector', render: (v?: string) => v || '-' },
    {
      title: '配置效应',
      dataIndex: 'allocation',
      render: (v?: number) => (v != null ? <span className="tabular-nums">{`${v >= 0 ? '+' : ''}${v.toFixed(2)}%`}</span> : '-'),
    },
    {
      title: '选股效应',
      dataIndex: 'selection',
      render: (v?: number) => (v != null ? <span className="tabular-nums">{`${v >= 0 ? '+' : ''}${v.toFixed(2)}%`}</span> : '-'),
    },
    {
      title: '交互效应',
      dataIndex: 'interaction',
      render: (v?: number) => (v != null ? <span className="tabular-nums">{`${v >= 0 ? '+' : ''}${v.toFixed(2)}%`}</span> : '-'),
    },
    {
      title: '合计',
      dataIndex: 'total',
      render: (v?: number) => (v != null ? <span className="tabular-nums">{`${v >= 0 ? '+' : ''}${v.toFixed(2)}%`}</span> : '-'),
    },
  ];

  const overviewMetrics = [
    { title: <HelpPopover termKey="total_return">总收益</HelpPopover>, value: metrics.total_return, suffix: '%' },
    { title: <HelpPopover termKey="annualized_return">年化收益</HelpPopover>, value: metrics.annualized_return, suffix: '%' },
    { title: <HelpPopover termKey="max_drawdown_1y">最大回撤</HelpPopover>, value: metrics.max_drawdown, suffix: '%' },
    { title: <HelpPopover termKey="sharpe_ratio">夏普比率</HelpPopover>, value: metrics.sharpe_ratio },
    { title: <HelpPopover termKey="win_rate">胜率</HelpPopover>, value: metrics.win_rate, suffix: '%' },
    { title: <HelpPopover termKey="trade_count">交易次数</HelpPopover>, value: metrics.trade_count, precision: undefined },
  ];

  const overviewTab = (
    <div className="detail-tab-panel">
      <Panel title={`回测详情 #${data.id}`} padding="md" extra={<HelpTrigger tooltip="AI 解释回测指标" onClick={handleOpenHelp} />}>
        <ResponsiveGrid cols={3} gap="md">
          {overviewMetrics.map((m, idx) => (
            <Statistic
              key={idx}
              title={m.title}
              value={m.value}
              suffix={m.suffix}
              precision={m.precision !== undefined ? m.precision : 2}
            />
          ))}
        </ResponsiveGrid>
      </Panel>

      <Panel title={<HelpPopover termKey="nav_curve">净值曲线</HelpPopover>} padding="md">
        <ReactECharts option={navOption} className="detail-chart" />
      </Panel>
    </div>
  );

  const attributionTab = (
    <div className="detail-tab-panel">
      <Panel title="归因概览" padding="md">
        <ResponsiveGrid cols={3} gap="md">
          {[
            { title: '策略收益', value: attribution?.total_return, suffix: '%' },
            { title: '基准收益', value: attribution?.benchmark_return, suffix: '%' },
            { title: '超额收益', value: attribution?.excess_return, suffix: '%' },
            { title: '配置贡献', value: attribution?.summary?.allocation_pct, suffix: '%' },
            { title: '选股贡献', value: attribution?.summary?.selection_pct, suffix: '%' },
            { title: '交互贡献', value: attribution?.summary?.interaction_pct, suffix: '%' },
          ].map((m) => (
            <Statistic key={m.title} title={m.title} value={m.value} suffix={m.suffix} precision={2} />
          ))}
        </ResponsiveGrid>
      </Panel>

      <Panel title="归因明细" padding="md">
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

      <Panel title="交易统计" padding="md">
        <ResponsiveGrid cols={3} gap="md">
          {[
            { title: '总交易次数', value: attribution?.trade_stats?.total_trades, suffix: undefined },
            { title: '盈利次数', value: attribution?.trade_stats?.winning_trades, suffix: undefined },
            { title: '亏损次数', value: attribution?.trade_stats?.losing_trades, suffix: undefined },
            { title: '胜率', value: attribution?.trade_stats?.win_rate, suffix: '%' },
            { title: '平均收益', value: attribution?.trade_stats?.avg_return, suffix: '%' },
          ].map((m) => (
            <Statistic key={m.title} title={m.title} value={m.value} suffix={m.suffix} precision={m.suffix === '%' ? 2 : 0} />
          ))}
        </ResponsiveGrid>
      </Panel>
    </div>
  );

  const tradesTab = (
    <div className="detail-tab-panel">
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
    </div>
  );

  const tabItems = [
    { key: 'overview', label: '概览', children: overviewTab },
    { key: 'attribution', label: '绩效归因', children: attributionTab },
    { key: 'trades', label: '交易记录', children: tradesTab },
  ];

  const dateRange = (data.daily_nav && data.daily_nav.length > 0)
    ? `${data.daily_nav[0].date} ~ ${data.daily_nav[data.daily_nav.length - 1].date}`
    : null;

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow={<span><ExperimentOutlined className="detail-eyebrow-icon" />回测 #{data.id}</span>}
        title={`回测详情 #${data.id}`}
        description={
          [
            data.strategy_id ? `策略 ID：${data.strategy_id}` : null,
            dateRange,
            data.created_at ? `创建于 ${formatDateTime(data.created_at)}` : null,
          ].filter(Boolean).join(' · ')
        }
        extra={<HelpTrigger tooltip="AI 解释回测指标" onClick={handleOpenHelp} />}
      />

      <SectionHeading title="核心指标" />
      <ResponsiveGrid cols={4} gap="md" className="detail-section">
        {kpiItems.map((kpi) => (
          <div key={kpi.label} className={kpi.color}>
            <StatCard
              title={kpi.label}
              value={kpi.value != null ? formatSigned(kpi.value) : '—'}
              suffix={kpi.suffix}
            />
          </div>
        ))}
      </ResponsiveGrid>

      <Tabs items={tabItems} defaultActiveKey="overview" />
    </PageShell>
  );
}
