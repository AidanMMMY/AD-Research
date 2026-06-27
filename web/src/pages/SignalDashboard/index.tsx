import { Table, Row, Col, Statistic } from 'antd';
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
      <Row gutter={[16, 16]} style={{ marginBottom: 'var(--space-md)' }}>
        <Col xs={8}><GlassCard><Statistic title="买入信号" value={buyCount} valueStyle={{ color: 'var(--color-rise)' }} /></GlassCard></Col>
        <Col xs={8}><GlassCard><Statistic title="卖出信号" value={sellCount} valueStyle={{ color: 'var(--color-fall)' }} /></GlassCard></Col>
        <Col xs={8}><GlassCard><Statistic title="持有信号" value={holdCount} /></GlassCard></Col>
      </Row>

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
