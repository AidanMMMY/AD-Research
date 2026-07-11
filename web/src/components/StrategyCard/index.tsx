import { Button, Descriptions, Tag } from 'antd';
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
    <div className="strategy-card">
      <div className="strategy-card__body">
        <div className="strategy-card__header">
          <h3 className="strategy-card__title">{strategy.name}</h3>
          <ThemeTag variant="accent">{FAMILY_LABELS[strategy.family] || strategy.family}</ThemeTag>
        </div>
        <p className="strategy-card__description">{strategy.description}</p>
        <div className="strategy-card__params">
          {paramEntries.length > 0 && (
            <Descriptions size="small" column={2} className="strategy-card__params-list">
              {paramEntries.slice(0, 4).map(([key, spec]) => (
                <Descriptions.Item key={key} label={spec.label}>
                  <Tag className="strategy-card__param-tag">
                    {String(spec.default)}
                  </Tag>
                </Descriptions.Item>
              ))}
            </Descriptions>
          )}
          {paramEntries.length > 4 && (
            <p className="strategy-card__more">等 {paramEntries.length} 个参数</p>
          )}
        </div>
      </div>
      <div className="strategy-card__actions">
        <Button
          type="link"
          icon={<ExperimentOutlined />}
          onClick={() => onCreateConfig(strategy)}
        >
          创建配置
        </Button>
        <Button
          type="link"
          icon={<ThunderboltOutlined />}
          onClick={() => onRunStrategy(strategy)}
        >
          运行
        </Button>
        <Button
          type="link"
          icon={<PlayCircleOutlined />}
          onClick={() => onBacktest(strategy)}
        >
          回测
        </Button>
      </div>
    </div>
  );
}
