import { Button } from 'antd';
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

/** 卡片上最多展示的参数数，超出折叠为 "+N" */
const MAX_VISIBLE_PARAMS = 4;

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
  const visibleParams = paramEntries.slice(0, MAX_VISIBLE_PARAMS);
  const hiddenCount = paramEntries.length - visibleParams.length;

  return (
    <div className="strategy-card">
      <div className="strategy-card__body">
        <div className="strategy-card__header">
          <h3 className="strategy-card__title" title={strategy.name}>
            {strategy.name}
          </h3>
          <ThemeTag variant="accent" className="strategy-card__family">
            {FAMILY_LABELS[strategy.family] || strategy.family}
          </ThemeTag>
        </div>
        <p className="strategy-card__description">{strategy.description}</p>
        {paramEntries.length > 0 && (
          <dl className="strategy-card__params">
            {visibleParams.map(([key, spec]) => (
              <div key={key} className="strategy-card__param">
                <dt className="strategy-card__param-label">{spec.label}</dt>
                <dd className="strategy-card__param-value">{String(spec.default)}</dd>
              </div>
            ))}
            {hiddenCount > 0 && (
              <div className="strategy-card__param strategy-card__param--more">
                <dt className="strategy-card__param-label">更多</dt>
                <dd className="strategy-card__param-value">+{hiddenCount}</dd>
              </div>
            )}
          </dl>
        )}
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
