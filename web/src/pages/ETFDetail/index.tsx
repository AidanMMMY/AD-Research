import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Card, Tabs, Row, Col, Statistic, Spin, Descriptions, Radio, Checkbox, Space, Alert, Button, message } from 'antd';
import { StarOutlined, StarFilled } from '@ant-design/icons';
import { useETFDetail } from '@/hooks/useETFList';
import { useETFScore } from '@/hooks/useScores';
import { useFavoriteStatus } from '@/hooks/useFavorites';
import { marketApi } from '@/api';
import { useQuery } from '@tanstack/react-query';
import KLineChart, { DEFAULT_OVERLAYS } from '@/components/KLineChart';
import ScoreRadar from '@/components/ScoreRadar';
import { formatPercent } from '@/utils/format';

const TIME_RANGE_OPTIONS = [
  { label: '30日', value: 30 },
  { label: '60日', value: 60 },
  { label: '120日', value: 120 },
  { label: '250日', value: 250 },
];

const INDICATOR_OPTIONS = [
  { label: 'MA5', value: 'ma5' },
  { label: 'MA10', value: 'ma10' },
  { label: 'MA20', value: 'ma20' },
  { label: 'MA60', value: 'ma60' },
  { label: '布林带', value: 'bb' },
  { label: 'RSI14', value: 'rsi' },
  { label: 'MACD', value: 'macd' },
];

export default function ETFDetail() {
  const { code } = useParams<{ code: string }>();
  const { data: etf, isLoading: etfLoading, error: etfError } = useETFDetail(code || '');
  const { data: score } = useETFScore(code || '');
  const { isFavorite, isLoading: favLoading, toggle, isToggling } = useFavoriteStatus(code || '');
  const [timeRange, setTimeRange] = useState(120);

  // Persist K-line overlay preferences in localStorage
  const [overlays, setOverlays] = useState(() => {
    try {
      const saved = localStorage.getItem('etf-detail-overlays');
      return saved ? { ...DEFAULT_OVERLAYS, ...JSON.parse(saved) } : DEFAULT_OVERLAYS;
    } catch {
      return DEFAULT_OVERLAYS;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem('etf-detail-overlays', JSON.stringify(overlays));
    } catch {
      // ignore storage errors
    }
  }, [overlays]);

  const handleToggleFavorite = async () => {
    try {
      const result = await toggle();
      message.success(result.data.message);
    } catch {
      message.error('操作失败');
    }
  };

  const { data: historyData, isLoading: historyLoading } = useQuery({
    queryKey: ['etf-history', code, timeRange],
    queryFn: () => marketApi.history(code || '', { limit: timeRange }).then((r) => r.data),
    enabled: !!code,
    retry: 1,
  });

  const { data: indicator } = useQuery({
    queryKey: ['etf-indicator', code],
    queryFn: () => marketApi.indicators(code || '').then((r) => r.data),
    enabled: !!code,
    retry: 1,
  });

  if (etfLoading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (etfError) return <Alert message="加载ETF信息失败" description={(etfError as Error).message} type="error" style={{ margin: 24 }} />;
  if (!etf) return <Alert message="ETF不存在" description={`未找到代码为 ${code} 的ETF`} type="warning" style={{ margin: 24 }} />;

  const safeHistoryItems = historyData?.items || [];

  const tabItems = [
    {
      key: 'kline',
      label: 'K线行情',
      children: (
        <div>
          <Card size="small" style={{ marginBottom: 12 }}>
            <Space size="large" wrap>
              <Space>
                <span>时间范围：</span>
                <Radio.Group
                  value={timeRange}
                  onChange={(e) => setTimeRange(e.target.value)}
                  optionType="button"
                  buttonStyle="solid"
                  size="small"
                >
                  {TIME_RANGE_OPTIONS.map((opt) => (
                    <Radio.Button key={opt.value} value={opt.value}>
                      {opt.label}
                    </Radio.Button>
                  ))}
                </Radio.Group>
              </Space>
              <Space>
                <span>技术指标：</span>
                <Checkbox.Group
                  value={Object.entries(overlays)
                    .filter(([, v]) => v)
                    .map(([k]) => k)}
                  onChange={(checkedValues) => {
                    const newOverlays: Record<string, boolean> = {};
                    INDICATOR_OPTIONS.forEach((opt) => {
                      newOverlays[opt.value] = checkedValues.includes(opt.value);
                    });
                    setOverlays(newOverlays as typeof overlays);
                  }}
                >
                  {INDICATOR_OPTIONS.map((opt) => (
                    <Checkbox key={opt.value} value={opt.value}>
                      {opt.label}
                    </Checkbox>
                  ))}
                </Checkbox.Group>
              </Space>
            </Space>
          </Card>
          {historyLoading ? <Spin /> : (
            safeHistoryItems.length ? (
              <KLineChart data={safeHistoryItems} overlays={overlays} />
            ) : (
              <Alert message="暂无历史行情数据" type="info" showIcon />
            )
          )}
        </div>
      ),
    },
    {
      key: 'indicators',
      label: '指标数据',
      children: (
        <Row gutter={[16, 16]}>
          <Col xs={12} sm={8} md={6}>
            <Card><Statistic title="RSI14" value={indicator?.rsi14} precision={1} /></Card>
          </Col>
          <Col xs={12} sm={8} md={6}>
            <Card><Statistic title="夏普1年" value={indicator?.sharpe_1y} precision={2} /></Card>
          </Col>
          <Col xs={12} sm={8} md={6}>
            <Card><Statistic title="波动率20日" value={indicator?.volatility_20d} precision={2} suffix="%" /></Card>
          </Col>
          <Col xs={12} sm={8} md={6}>
            <Card><Statistic title="最大回撤" value={indicator?.max_drawdown_1y} precision={2} suffix="%" /></Card>
          </Col>
          <Col xs={12} sm={8} md={6}>
            <Card><Statistic title="1月收益" value={indicator?.return_1m} precision={2} suffix="%" /></Card>
          </Col>
          <Col xs={12} sm={8} md={6}>
            <Card><Statistic title="3月收益" value={indicator?.return_3m} precision={2} suffix="%" /></Card>
          </Col>
          <Col xs={12} sm={8} md={6}>
            <Card><Statistic title="1年收益" value={indicator?.return_1y} precision={2} suffix="%" /></Card>
          </Col>
          <Col xs={12} sm={8} md={6}>
            <Card><Statistic title="MA5" value={indicator?.ma5} precision={2} /></Card>
          </Col>
        </Row>
      ),
    },
    {
      key: 'score',
      label: '综合评分',
      children: (
        score ? (
          <Row gutter={[16, 16]}>
            <Col xs={24} md={12}>
              <ScoreRadar data={score} />
            </Col>
            <Col xs={24} md={12}>
              <Card title="评分详情">
                <Descriptions column={1}>
                  <Descriptions.Item label="综合评分">{score.composite_score}</Descriptions.Item>
                  <Descriptions.Item label="全市场排名">{score.rank_overall}</Descriptions.Item>
                  <Descriptions.Item label="分类排名">{score.rank_category}</Descriptions.Item>
                  <Descriptions.Item label="收益得分">{score.score_return}</Descriptions.Item>
                  <Descriptions.Item label="风险得分">{score.score_risk}</Descriptions.Item>
                  <Descriptions.Item label="夏普得分">{score.score_sharpe}</Descriptions.Item>
                  <Descriptions.Item label="流动性得分">{score.score_liquidity}</Descriptions.Item>
                  <Descriptions.Item label="趋势得分">{score.score_trend}</Descriptions.Item>
                </Descriptions>
              </Card>
            </Col>
          </Row>
        ) : (
          <div>暂无评分数据</div>
        )
      ),
    },
  ];

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2 style={{ margin: 0 }}>{etf.code} {etf.name}</h2>
            <div style={{ color: '#888', fontSize: 14 }}>
              {etf.category || '—'} | {etf.market || '—'} | {etf.fund_manager || '—'}
              {etf.fund_size && ` | 规模: ${(etf.fund_size / 1e8).toFixed(1)}亿`}
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <Button
              type={isFavorite ? 'primary' : 'default'}
              icon={isFavorite ? <StarFilled /> : <StarOutlined />}
              loading={isToggling || favLoading}
              onClick={handleToggleFavorite}
            >
              {isFavorite ? '已收藏' : '收藏'}
            </Button>
            {indicator?.return_1m !== undefined && (
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 28, fontWeight: 'bold', color: indicator.return_1m >= 0 ? '#cf1322' : '#3f8600' }}>
                  {formatPercent(indicator.return_1m)}
                </div>
                <div style={{ color: '#888', fontSize: 12 }}>1月收益</div>
              </div>
            )}
          </div>
        </div>
      </Card>

      <Tabs items={tabItems} defaultActiveKey="kline" />
    </div>
  );
}
