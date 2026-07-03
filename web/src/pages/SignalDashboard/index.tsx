import { useMemo, useState } from 'react';
import { Table, Select, Space } from 'antd';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import FilterToolbar from '@/components/FilterToolbar';
import EmptyState from '@/components/EmptyState';
import ThemeTag, { ThemeTagVariant } from '@/components/ThemeTag';
import HelpTrigger from '@/components/HelpTrigger';
import { useSignals } from '@/hooks/useSignals';
import { useAIHelp } from '@/hooks/useAIHelp';
import { buildSignalDashboardContext } from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';
import type { Signal } from '@/types/signal';

const SIGNAL_VARIANTS: Record<string, ThemeTagVariant> = {
  BUY: 'rise',
  SELL: 'fall',
  HOLD: 'default',
};

const SIGNAL_LABELS: Record<string, string> = {
  BUY: '买入',
  SELL: '卖出',
  HOLD: '持有',
};

const FAMILY_LABELS: Record<string, string> = {
  trend_following: '趋势跟踪',
  mean_reversion: '均值回归',
  momentum: '动量',
  volatility: '波动率',
  volume: '成交量',
  composite: '复合因子',
  cross_sectional: '横截面',
  event: '事件驱动',
};

export default function SignalDashboard() {
  const { data: signals, isLoading } = useSignals();
  const { open } = useAIHelp();
  const [familyFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');

  const items: Signal[] = signals?.items || [];

  const filteredItems = useMemo(() => {
    if (typeFilter === 'all' && familyFilter === 'all') {
      return items;
    }
    return items.filter((item) => {
      if (typeFilter !== 'all' && item.signal_type !== typeFilter) {
        return false;
      }
      return true;
    });
  }, [items, typeFilter, familyFilter]);

  const buyCount = filteredItems.filter((s) => s.signal_type === 'BUY').length;
  const sellCount = filteredItems.filter((s) => s.signal_type === 'SELL').length;
  const holdCount = filteredItems.filter((s) => s.signal_type === 'HOLD').length;

  const columns = [
    { title: '策略ID', dataIndex: 'strategy_id', width: 80, render: (v: any) => <span className="tabular-nums">{v}</span> },
    { title: '标的代码', dataIndex: 'etf_code' },
    {
      title: '名称',
      dataIndex: 'etf_name',
      render: (v: string | undefined | null) => v || '—',
    },
    { title: '日期', dataIndex: 'trade_date' },
    {
      title: '信号',
      dataIndex: 'signal_type',
      render: (v: string) => <ThemeTag variant={SIGNAL_VARIANTS[v]}>{SIGNAL_LABELS[v] || v}</ThemeTag>,
      width: 80,
    },
    { title: '强度', dataIndex: 'strength', width: 80, render: (v: any) => <span className="tabular-nums">{v}</span> },
  ];

  const handleOpenHelp = () => {
    open({
      pageType: 'signal_dashboard',
      pageTitle: '交易信号',
      contextData: buildSignalDashboardContext(filteredItems, columns),
      quickQuestions: getQuickQuestions('signal_dashboard'),
    });
  };

  const familyOptions = [
    { label: '全部家族', value: 'all' },
    ...Object.entries(FAMILY_LABELS).map(([key, label]) => ({ label, value: key })),
  ];

  const typeOptions = [
    { label: '全部信号', value: 'all' },
    { label: '买入', value: 'BUY' },
    { label: '卖出', value: 'SELL' },
    { label: '持有', value: 'HOLD' },
  ];

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="交易"
        title="信号看板"
        description="查看最新交易信号汇总，监控买入、卖出、持有信号分布"
      />

      <div className="phase5c-kpi-strip phase5c-kpi-strip--cols-3 phase5c-section">
        {[
          { title: '买入信号', value: buyCount, color: 'var(--color-rise)' },
          { title: '卖出信号', value: sellCount, color: 'var(--color-fall)' },
          { title: '持有信号', value: holdCount, color: 'var(--text-primary)' },
        ].map((m) => (
          <div key={m.title} className="phase5c-kpi-cell">
            <div className="phase5c-kpi-cell__label">{m.title}</div>
            <div
              className={`phase5c-kpi-cell__value tabular-nums ${
                m.color === 'var(--color-rise)'
                  ? 'phase5c-kpi-cell__value--rise'
                  : m.color === 'var(--color-fall)'
                    ? 'phase5c-kpi-cell__value--fall'
                    : 'phase5c-kpi-cell__value--primary'
              }`}
            >
              {m.value}
            </div>
          </div>
        ))}
      </div>

      <Panel
        variant="default"
        title="最新交易信号"
        extra={<HelpTrigger tooltip="AI 解释信号含义" onClick={handleOpenHelp} />}
      >
        <FilterToolbar total={filteredItems.length}>
          <Space>
            <Select
              value={typeFilter}
              onChange={setTypeFilter}
              options={typeOptions}
              className="phase5c-select--xs"
            />
            <Select
              value={familyFilter}
              onChange={() => undefined}
              options={familyOptions}
              className="phase5c-select--sm"
              disabled
              placeholder="家族筛选（待后端支持）"
            />
          </Space>
        </FilterToolbar>

        <div className="phase5c-table-wrap">
          <Table
            dataSource={filteredItems}
            columns={columns}
            rowKey="id"
            size="small"
            loading={isLoading}
            scroll={{ x: 'max-content' }}
            pagination={{ pageSize: 20 }}
            locale={{
              emptyText: <EmptyState title="暂无信号" description="当前没有符合条件的交易信号" />,
            }}
          />
        </div>
      </Panel>
    </PageShell>
  );
}
