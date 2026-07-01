import { Statistic } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import { useSettingsStore } from '@/stores/settings';
import { getReturnColor } from '@/utils/color';
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
  const colorConvention = useSettingsStore((s) => s.colorConvention);
  return (
    <GlassCard padding="sm">
      <div className="tabular-nums">
        <Statistic
          title={title}
          value={value ?? 0}
          precision={precision}
          suffix={suffix}
          prefix={prefix || (isPositive ? <ArrowUpOutlined /> : <ArrowDownOutlined />)}
          valueStyle={{ color: getReturnColor(value, colorConvention), fontSize: 20 }}
        />
      </div>
    </GlassCard>
  );
}
