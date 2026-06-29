import { Table } from 'antd';
import GlassCard from '@/components/GlassCard';
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

export default function SignalDashboard() {
  const { data: signals, isLoading } = useSignals();

  const items: Signal[] = signals?.items || [];

  const buyCount = items.filter((s) => s.signal_type === 'BUY').length;
  const sellCount = items.filter((s) => s.signal_type === 'SELL').length;
  const holdCount = items.filter((s) => s.signal_type === 'HOLD').length;

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

      <GlassCard title="最新交易信号">
        <Table
          dataSource={items}
          columns={columns}
          rowKey="id"
          size="small"
          loading={isLoading}
          scroll={{ x: 'max-content' }}
          pagination={{ pageSize: 20 }}
        />
      </GlassCard>
    </div>
  );
}
