import { Statistic } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import GlassCard from './GlassCard';

interface IndicatorCardProps {
  title: string;
  value?: number | null;
  suffix?: string;
  precision?: number;
  prefix?: React.ReactNode;
}

export default function IndicatorCard({ title, value, suffix, precision = 2, prefix }: IndicatorCardProps) {
  const isPositive = value !== undefined && value !== null && value >= 0;
  return (
    <GlassCard padding="sm">
      <Statistic
        title={title}
        value={value ?? 0}
        precision={precision}
        suffix={suffix}
        prefix={prefix || (isPositive ? <ArrowUpOutlined /> : <ArrowDownOutlined />)}
        valueStyle={{ color: isPositive ? '#ef4444' : '#22c55e', fontSize: 20 }}
      />
    </GlassCard>
  );
}
