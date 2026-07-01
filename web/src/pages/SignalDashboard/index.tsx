import { useMemo, useState } from 'react';
import { Table, Select, Space } from 'antd';
import Panel from '@/components/Panel';
import ThemeTag, { ThemeTagVariant } from '@/components/ThemeTag';
import { useSignals } from '@/hooks/useSignals';
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
    { title: '策略ID', dataIndex: 'strategy_id', width: 80 },
    { title: '标的代码', dataIndex: 'etf_code' },
    { title: '日期', dataIndex: 'trade_date' },
    {
      title: '信号',
      dataIndex: 'signal_type',
      render: (v: string) => <ThemeTag variant={SIGNAL_VARIANTS[v]}>{SIGNAL_LABELS[v] || v}</ThemeTag>,
      width: 80,
    },
    { title: '强度', dataIndex: 'strength', width: 80 },
  ];

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
    <div>
      <h1 style={{ fontSize: 'var(--text-h1-size)', fontWeight: 500, color: 'var(--text-primary)', margin: '0 0 8px', letterSpacing: '-0.03em' }}>信号看板</h1>
      <p style={{ margin: '0 0 32px', color: 'var(--text-tertiary)', fontSize: 'var(--text-body-size)' }}>查看最新交易信号汇总，监控买入、卖出、持有信号分布</p>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          borderTop: '1px solid var(--border-default)',
          borderBottom: '1px solid var(--border-default)',
          marginBottom: 'var(--space-md)',
        }}
      >
        {[
          { title: '买入信号', value: buyCount, color: 'var(--color-rise)' },
          { title: '卖出信号', value: sellCount, color: 'var(--color-fall)' },
          { title: '持有信号', value: holdCount, color: 'var(--text-primary)' },
        ].map((m, i) => (
          <div
            key={m.title}
            style={{
              padding: '20px 16px',
              borderRight: i < 2 ? '1px solid var(--border-default)' : 'none',
            }}
          >
            <div
              style={{
                fontSize: 'var(--text-label-size)',
                color: 'var(--text-tertiary)',
                fontWeight: 500,
                marginBottom: '12px',
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
              }}
            >
              {m.title}
            </div>
            <div
              style={{
                fontSize: 'var(--text-data-lg-size)',
                fontWeight: 400,
                color: m.color,
                fontFamily: 'var(--font-mono)',
                lineHeight: 1.2,
              }}
            >
              {m.value}
            </div>
          </div>
        ))}
      </div>

      <Panel variant="minimal" title="最新交易信号" extra={
        <Space>
          <Select
            value={typeFilter}
            onChange={setTypeFilter}
            options={typeOptions}
            style={{ width: 120 }}
          />
          <Select
            value={familyFilter}
            onChange={() => undefined}
            options={familyOptions}
            style={{ width: 140 }}
            disabled
            placeholder="家族筛选（待后端支持）"
          />
        </Space>
      }>
        <Table
          dataSource={filteredItems}
          columns={columns}
          rowKey="id"
          size="small"
          loading={isLoading}
          scroll={{ x: 'max-content' }}
          pagination={{ pageSize: 20 }}
        />
      </Panel>
    </div>
  );
}
