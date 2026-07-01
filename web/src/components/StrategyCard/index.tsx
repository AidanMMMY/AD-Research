import { Card, Button, Descriptions, Tag } from 'antd';
import { ExperimentOutlined, PlayCircleOutlined, ThunderboltOutlined } from '@ant-design/icons';
import ThemeTag from '@/components/ThemeTag';
import type { StrategyCatalogItem } from '@/types/strategy';

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

interface StrategyCardProps {
  strategy: StrategyCatalogItem;
  onCreateConfig: (strategy: StrategyCatalogItem) => void;
  onRunStrategy: (strategy: StrategyCatalogItem) => void;
  onBacktest: (strategy: StrategyCatalogItem) => void;
}

export default function StrategyCard({
  strategy,
  onCreateConfig,
  onRunStrategy,
  onBacktest,
}: StrategyCardProps) {
  const paramEntries = Object.entries(strategy.param_specs);

  return (
    <Card
      hoverable
      style={{
        background: 'var(--surface-elevated)',
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-md)',
      }}
      bodyStyle={{ padding: 'var(--space-md)' }}
      actions={[
        <Button
          key="create"
          type="link"
          icon={<ExperimentOutlined />}
          onClick={() => onCreateConfig(strategy)}
        >
          创建配置
        </Button>,
        <Button
          key="run"
          type="link"
          icon={<ThunderboltOutlined />}
          onClick={() => onRunStrategy(strategy)}
        >
          运行
        </Button>,
        <Button
          key="backtest"
          type="link"
          icon={<PlayCircleOutlined />}
          onClick={() => onBacktest(strategy)}
        >
          回测
        </Button>,
      ]}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
        <h3
          style={{
            margin: 0,
            fontSize: 'var(--text-h3-size)',
            fontWeight: 500,
            color: 'var(--text-primary)',
          }}
        >
          {strategy.name}
        </h3>
        <ThemeTag variant="accent">{FAMILY_LABELS[strategy.family] || strategy.family}</ThemeTag>
      </div>
      <p style={{ margin: '0 0 12px', color: 'var(--text-secondary)', fontSize: 'var(--text-body-size)' }}>
        {strategy.description}
      </p>
      {paramEntries.length > 0 && (
        <Descriptions size="small" column={2} style={{ marginBottom: 0 }}>
          {paramEntries.slice(0, 4).map(([key, spec]) => (
            <Descriptions.Item key={key} label={spec.label}>
              <Tag style={{ background: 'var(--surface-default)', borderColor: 'var(--border-default)' }}>
                {String(spec.default)}
              </Tag>
            </Descriptions.Item>
          ))}
        </Descriptions>
      )}
      {paramEntries.length > 4 && (
        <p style={{ margin: '8px 0 0', color: 'var(--text-tertiary)', fontSize: 12 }}>
          等 {paramEntries.length} 个参数
        </p>
      )}
    </Card>
  );
}
