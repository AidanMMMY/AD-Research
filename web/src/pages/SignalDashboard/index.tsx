import { Table, Tag, Row, Col, Statistic } from 'antd';
import GlassCard from '@/components/GlassCard';
import { useSignals } from '@/hooks/useSignals';
import type { Signal } from '@/types/signal';

const SIGNAL_COLORS: Record<string, string> = {
  BUY: 'red',
  SELL: 'green',
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
    { title: 'ETF代码', dataIndex: 'etf_code' },
    { title: '日期', dataIndex: 'trade_date' },
    {
      title: '信号',
      dataIndex: 'signal_type',
      render: (v: string) => <Tag color={SIGNAL_COLORS[v]}>{SIGNAL_LABELS[v] || v}</Tag>,
      width: 80,
    },
    { title: '强度', dataIndex: 'strength', width: 80 },
  ];

  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={8}><GlassCard><Statistic title="买入信号" value={buyCount} valueStyle={{ color: '#ef4444' }} /></GlassCard></Col>
        <Col xs={8}><GlassCard><Statistic title="卖出信号" value={sellCount} valueStyle={{ color: '#22c55e' }} /></GlassCard></Col>
        <Col xs={8}><GlassCard><Statistic title="持有信号" value={holdCount} /></GlassCard></Col>
      </Row>

      <GlassCard title="最新交易信号">
        <Table
          dataSource={items}
          columns={columns}
          rowKey="id"
          size="small"
          loading={isLoading}
          pagination={{ pageSize: 20 }}
        />
      </GlassCard>
    </div>
  );
}
