import { Statistic } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined, MinusOutlined } from '@ant-design/icons';
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

function getDirectionIcon(value?: number | null) {
  if (value === undefined || value === null || value === 0) return <MinusOutlined />;
  return value > 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />;
}

export default function IndicatorCard({ title, value, suffix, precision = 2, prefix }: IndicatorCardProps) {
  const colorConvention = useSettingsStore((s) => s.colorConvention);
  return (
    <GlassCard padding="sm">
      <div className="tabular-nums">
        <Statistic
          title={title}
          value={value ?? 0}
          precision={precision}
          suffix={suffix}
          prefix={prefix || getDirectionIcon(value)}
          valueStyle={{ color: getReturnColor(value, colorConvention), fontSize: 20 }}
        />
      </div>
    </GlassCard>
  );
}
