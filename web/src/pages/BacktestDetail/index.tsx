import { useParams, useNavigate } from 'react-router-dom';
import { Statistic, Table, Spin, Tabs, Alert, Button } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined, ExperimentOutlined } from '@ant-design/icons';
import Panel from '@/components/Panel';
import PageHeader from '@/components/PageHeader';
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
import dayjs from 'dayjs';

export default function BacktestDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data, isLoading, error } = useBacktestDetail(id || '');
  const { data: attribution, isLoading: attributionLoading } = useAttribution(id || '');
  const { open } = useAIHelp();
  const isMobile = useIsMobile();

  if (isLoading) {
    return (
      <div role="status" aria-live="polite" style={{ padding: 'var(--space-9) 0', textAlign: 'center' }}>
        <Spin size="large" />
        <div style={{ marginTop: 'var(--space-4)', color: 'var(--text-tertiary)', fontSize: 'var(--text-body-size)' }}>
          正在加载回测结果…
        </div>
      </div>
    );
  }
  if (error) {
    return (
      <div style={{ marginTop: 'var(--space-6)' }}>
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
    );
  }
  if (!data) {
    return (
      <div style={{ marginTop: 'var(--space-6)' }}>
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
          className="tabular-nums"
          style={{ color: v >= 0 ? 'var(--color-rise)' : 'var(--color-fall)', display: 'inline-flex', alignItems: 'baseline', gap: 2 }}
        >
          {v > 0 ? (
            <ArrowUpOutlined style={{ fontSize: '0.85em' }} aria-label="up" />
          ) : v < 0 ? (
            <ArrowDownOutlined style={{ fontSize: '0.85em' }} aria-label="down" />
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
        <div className="tabular-nums" style={{ ...gridStyle, borderTop: 'none' }}>
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
        <div className="tabular-nums" style={gridStyle}>
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
        <div className="tabular-nums" style={gridStyle}>
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

  // Build a compact meta line: strategy type, date range, status.
  const dateRange = (data.daily_nav && data.daily_nav.length > 0)
    ? `${data.daily_nav[0].date} ~ ${data.daily_nav[data.daily_nav.length - 1].date}`
    : null;

  return (
    <div>
      <PageHeader
        eyebrow={<span><ExperimentOutlined style={{ marginRight: 6 }} />回测 #{data.id}</span>}
        title={`回测详情 #${data.id}`}
        description={
          [
            data.strategy_id ? `策略 ID：${data.strategy_id}` : null,
            dateRange,
            data.created_at ? `创建于 ${dayjs(data.created_at).format('YYYY-MM-DD HH:mm')}` : null,
          ].filter(Boolean).join(' · ')
        }
        extra={
          <HelpTrigger tooltip="AI 解释回测指标" onClick={handleOpenHelp} />
        }
      />

      {/* Hero KPI strip — the page's single visual anchor. */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: isMobile ? 'repeat(2, 1fr)' : 'repeat(4, 1fr)',
          borderTop: '1px solid var(--border-default)',
          borderBottom: '1px solid var(--border-default)',
          marginBottom: 'var(--space-5)',
        }}
      >
        {[
          {
            label: '总收益',
            value: metrics.total_return,
            suffix: '%',
            colorKey: 'total_return',
          },
          {
            label: '夏普比率',
            value: metrics.sharpe_ratio,
            suffix: undefined,
            colorKey: 'sharpe',
          },
          {
            label: '最大回撤',
            value: metrics.max_drawdown,
            suffix: '%',
            colorKey: 'drawdown',
          },
          {
            label: '胜率',
            value: metrics.win_rate,
            suffix: '%',
            colorKey: 'win_rate',
          },
        ].map((kpi, i) => {
          const isLastCol = (i + 1) % (isMobile ? 2 : 4) === 0;
          const color = kpi.value == null
            ? 'var(--text-tertiary)'
            : kpi.colorKey === 'drawdown'
              ? 'var(--color-fall)'
              : kpi.colorKey === 'total_return'
                ? (kpi.value >= 0 ? 'var(--color-rise)' : 'var(--color-fall)')
                : 'var(--text-primary)';
          return (
            <div
              key={kpi.label}
              style={{
                padding: '20px 16px',
                borderRight: isLastCol ? 'none' : '1px solid var(--border-default)',
              }}
            >
              <div
                style={{
                  fontSize: 'var(--text-label-size)',
                  color: 'var(--text-tertiary)',
                  fontWeight: 500,
                  marginBottom: 12,
                  letterSpacing: '0.12em',
                  textTransform: 'uppercase',
                }}
              >
                {kpi.label}
              </div>
              <div
                className="tabular-nums"
                style={{
                  fontSize: 'var(--text-data-xl-size)',
                  fontWeight: 400,
                  color,
                  fontFamily: 'var(--font-mono)',
                  lineHeight: 1.1,
                  letterSpacing: '-0.02em',
                }}
              >
                {kpi.value != null
                  ? (
                    <>
                      {typeof kpi.value === 'number' ? kpi.value.toFixed(2) : kpi.value}
                      {kpi.suffix && (
                        <span style={{ fontSize: 'var(--text-body-size)', color: 'var(--text-tertiary)', marginLeft: 4, fontWeight: 500 }}>
                          {kpi.suffix}
                        </span>
                      )}
                    </>
                  )
                  : <span style={{ color: 'var(--text-tertiary)' }}>—</span>}
              </div>
            </div>
          );
        })}
      </div>

      <Tabs items={tabItems} defaultActiveKey="overview" />
    </div>
  );
}
