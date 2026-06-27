import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Tabs, Row, Col, Statistic, Spin, Descriptions, Radio, Checkbox, Space, Alert, Button, message, Tag, Skeleton } from 'antd';
import { StarOutlined, StarFilled, RobotOutlined, ReadOutlined, SmileOutlined } from '@ant-design/icons';
import { useETFDetail } from '@/hooks/useETFList';
import { useETFScore } from '@/hooks/useScores';
import { useFavoriteStatus } from '@/hooks/useFavorites';
import { useAIHelp } from '@/hooks/useAIHelp';
import { marketApi, researchApi } from '@/api';
import { useQuery } from '@tanstack/react-query';
import KLineChart, { DEFAULT_OVERLAYS } from '@/components/KLineChart';
import ScoreRadar from '@/components/ScoreRadar';
import Panel from '@/components/Panel';
import HelpTrigger from '@/components/HelpTrigger';
import HelpPopover from '@/components/HelpPopover';
import { formatPercent } from '@/utils/format';
import { useSettingsStore } from '@/stores/settings';
import { getReturnColor, getUpColor, getDownColor } from '@/utils/color';
import { buildETFDetailContext } from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';
import type { ResearchNote } from '@/api/research';

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

const INDICATOR_OPTION_TERMS: Record<string, string> = {
  ma5: 'ma5',
  ma10: 'ma10',
  ma20: 'ma20',
  ma60: 'ma60',
  bb: 'bollinger_bands',
  rsi: 'rsi14',
  macd: 'macd',
};

const SENTIMENT_COLORS: Record<string, string> = {
  bullish: getUpColor(),
  positive: getUpColor(),
  bearish: getDownColor(),
  negative: getDownColor(),
  neutral: '#eab308',
};

const SENTIMENT_LABELS: Record<string, string> = {
  bullish: '看多',
  positive: '看多',
  bearish: '看空',
  negative: '看空',
  neutral: '中性',
};

export default function ETFDetail() {
  const { code } = useParams<{ code: string }>();
  const navigate = useNavigate();
  const { open } = useAIHelp();
  const colorConvention = useSettingsStore((s) => s.colorConvention);
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

  // AI Analysis data
  const { data: researchNotes, isLoading: notesLoading } = useQuery({
    queryKey: ['research-notes', code],
    queryFn: () => researchApi.getNotes(code || '').then((r) => r.data),
    enabled: !!code,
  });

  const { data: sentiment, isLoading: sentimentLoading } = useQuery({
    queryKey: ['sentiment', code],
    queryFn: () => researchApi.getSentiment(code || '').then((r) => r.data),
    enabled: !!code,
  });

  if (etfLoading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (etfError) return <Alert message="加载标的详情失败" description={(etfError as Error).message} type="error" style={{ margin: 24 }} />;
  if (!etf) return <Alert message="标的不存在" description={`未找到代码为 ${code} 的标的`} type="warning" style={{ margin: 24 }} />;

  const handleOpenHelp = () => {
    open({
      pageType: 'etf_detail',
      pageTitle: `ETF 详情 - ${etf.name || code}`,
      contextData: buildETFDetailContext(code, etf, score, indicator, sentiment, timeRange),
      quickQuestions: getQuickQuestions('etf_detail'),
    });
  };

  const safeHistoryItems = historyData?.items || [];
  const latestNote: ResearchNote | null = researchNotes?.[0] || null;

  const tabItems = [
    {
      key: 'kline',
      label: 'K线行情',
      children: (
        <div>
          <div style={{ padding: 'var(--space-3) 0', borderBottom: '1px solid var(--border-default)', marginBottom: 'var(--space-4)' }}>
            <Space size="large" wrap>
              <Space>
                <HelpPopover termKey="time_range">时间范围</HelpPopover>：
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
                      <HelpPopover termKey={INDICATOR_OPTION_TERMS[opt.value]}>{opt.label}</HelpPopover>
                    </Checkbox>
                  ))}
                </Checkbox.Group>
              </Space>
            </Space>
          </div>
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
        <div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
            <HelpTrigger tooltip="AI 解释技术指标" onClick={handleOpenHelp} />
          </div>
          <Row gutter={[16, 16]}>
            <Col xs={12} sm={8} md={6}>
              <div style={{ borderBottom: '1px solid var(--border-default)', padding: 'var(--space-3) 0' }}>
                <Statistic title={<HelpPopover termKey="rsi14">RSI14</HelpPopover>} value={indicator?.rsi14} precision={1} />
              </div>
            </Col>
            <Col xs={12} sm={8} md={6}>
              <div style={{ borderBottom: '1px solid var(--border-default)', padding: 'var(--space-3) 0' }}>
                <Statistic title={<HelpPopover termKey="sharpe_1y">夏普1年</HelpPopover>} value={indicator?.sharpe_1y} precision={2} />
              </div>
            </Col>
            <Col xs={12} sm={8} md={6}>
              <div style={{ borderBottom: '1px solid var(--border-default)', padding: 'var(--space-3) 0' }}>
                <Statistic title={<HelpPopover termKey="volatility_20d">波动率20日</HelpPopover>} value={indicator?.volatility_20d} precision={2} suffix="%" />
              </div>
            </Col>
            <Col xs={12} sm={8} md={6}>
              <div style={{ borderBottom: '1px solid var(--border-default)', padding: 'var(--space-3) 0' }}>
                <Statistic title={<HelpPopover termKey="max_drawdown_1y">最大回撤</HelpPopover>} value={indicator?.max_drawdown_1y} precision={2} suffix="%" />
              </div>
            </Col>
            <Col xs={12} sm={8} md={6}>
              <div style={{ borderBottom: '1px solid var(--border-default)', padding: 'var(--space-3) 0' }}>
                <Statistic title={<HelpPopover termKey="return_1m">1月收益</HelpPopover>} value={indicator?.return_1m} precision={2} suffix="%" />
              </div>
            </Col>
            <Col xs={12} sm={8} md={6}>
              <div style={{ borderBottom: '1px solid var(--border-default)', padding: 'var(--space-3) 0' }}>
                <Statistic title={<HelpPopover termKey="return_3m">3月收益</HelpPopover>} value={indicator?.return_3m} precision={2} suffix="%" />
              </div>
            </Col>
            <Col xs={12} sm={8} md={6}>
              <div style={{ borderBottom: '1px solid var(--border-default)', padding: 'var(--space-3) 0' }}>
                <Statistic title={<HelpPopover termKey="return_1y">1年收益</HelpPopover>} value={indicator?.return_1y} precision={2} suffix="%" />
              </div>
            </Col>
            <Col xs={12} sm={8} md={6}>
              <div style={{ borderBottom: '1px solid var(--border-default)', padding: 'var(--space-3) 0' }}>
                <Statistic title={<HelpPopover termKey="ma5">MA5</HelpPopover>} value={indicator?.ma5} precision={2} />
              </div>
            </Col>
          </Row>
        </div>
      ),
    },
    {
      key: 'score',
      label: '综合评分',
      children: (
        score ? (
          <div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
              <HelpTrigger tooltip="AI 解释评分维度" onClick={handleOpenHelp} />
            </div>
            <Row gutter={[16, 16]}>
              <Col xs={24} md={12}>
                <ScoreRadar data={score} />
              </Col>
              <Col xs={24} md={12}>
                <Panel variant="minimal" title="评分详情" padding="md">
                  <Descriptions column={1}>
                    <Descriptions.Item label={<HelpPopover termKey="composite_score">综合评分</HelpPopover>}>{score.composite_score}</Descriptions.Item>
                    <Descriptions.Item label={<HelpPopover termKey="rank_overall">全市场排名</HelpPopover>}>{score.rank_overall}</Descriptions.Item>
                    <Descriptions.Item label={<HelpPopover termKey="rank_category">分类排名</HelpPopover>}>{score.rank_category}</Descriptions.Item>
                    <Descriptions.Item label={<HelpPopover termKey="score_return">收益得分</HelpPopover>}>{score.score_return}</Descriptions.Item>
                    <Descriptions.Item label={<HelpPopover termKey="score_risk">风险得分</HelpPopover>}>{score.score_risk}</Descriptions.Item>
                    <Descriptions.Item label={<HelpPopover termKey="score_sharpe">夏普得分</HelpPopover>}>{score.score_sharpe}</Descriptions.Item>
                    <Descriptions.Item label={<HelpPopover termKey="score_liquidity">流动性得分</HelpPopover>}>{score.score_liquidity}</Descriptions.Item>
                    <Descriptions.Item label={<HelpPopover termKey="score_trend">趋势得分</HelpPopover>}>{score.score_trend}</Descriptions.Item>
                  </Descriptions>
                </Panel>
              </Col>
            </Row>
          </div>
        ) : (
          <div>暂无评分数据</div>
        )
      ),
    },
    {
      key: 'ai',
      label: (
        <span>
          <RobotOutlined style={{ marginRight: 4 }} />
          AI分析
        </span>
      ),
      children: (
        <div>
          {notesLoading || sentimentLoading ? (
            <Skeleton active paragraph={{ rows: 8 }} />
          ) : (
            <Row gutter={[16, 16]}>
              {/* Latest Research Note */}
              <Col xs={24} md={12}>
                <Panel
                  variant="minimal"
                  title={<span><ReadOutlined style={{ marginRight: 6 }} /><HelpPopover termKey="ai_research_note">AI 研究笔记</HelpPopover></span>}
                  extra={
                    <Button
                      size="small"
                      type="primary"
                      icon={<RobotOutlined />}
                      onClick={() => {
                        researchApi.generateNote(code || '').then(() => {
                          message.success('研报生成中，请稍后刷新');
                        }).catch(() => message.error('生成失败'));
                      }}
                    >
                      生成研报
                    </Button>
                  }
                  padding="md"
                >
                  {latestNote ? (
                    <div>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                        {latestNote.sentiment && (
                          <Tag color={SENTIMENT_COLORS[latestNote.sentiment] || 'var(--text-secondary)'}>
                            {SENTIMENT_LABELS[latestNote.sentiment] || latestNote.sentiment}
                          </Tag>
                        )}
                        {latestNote.confidence && (
                          <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                            置信度 {latestNote.confidence}/10
                          </span>
                        )}
                        <span style={{ fontSize: 11, color: 'var(--text-tertiary)', marginLeft: 'auto' }}>
                          {latestNote.generated_at?.slice(0, 16) || latestNote.created_at?.slice(0, 16)}
                        </span>
                      </div>
                      <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                        {latestNote.summary}
                      </p>
                      <Button
                        type="link"
                        size="small"
                        onClick={() => navigate(`/research`)}
                        style={{ padding: 0 }}
                      >
                        查看全部研报 →
                      </Button>
                    </div>
                  ) : (
                    <div style={{ textAlign: 'center', padding: 24, color: 'var(--text-tertiary)' }}>
                      <RobotOutlined style={{ fontSize: 32, marginBottom: 8, display: 'block' }} />
                      <p>暂无AI研报</p>
                      <p style={{ fontSize: 12 }}>点击上方"生成研报"按钮开始分析</p>
                    </div>
                  )}
                </Panel>
              </Col>

              {/* Sentiment Gauge */}
              <Col xs={24} md={12}>
                <Panel
                  variant="minimal"
                  title={<span><SmileOutlined style={{ marginRight: 6 }} /><HelpPopover termKey="market_sentiment">市场情绪</HelpPopover></span>}
                  padding="md"
                >
                  {sentiment ? (
                    <div style={{ textAlign: 'center' }}>
                      {/* Score display */}
                      <div style={{ fontSize: 48, fontWeight: 700, color: SENTIMENT_COLORS[sentiment.label] || 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                        {sentiment.avg_score.toFixed(2)}
                      </div>
                      <Tag
                        color={SENTIMENT_COLORS[sentiment.label] || 'var(--text-secondary)'}
                        style={{ fontSize: 13, padding: '2px 12px', marginTop: 4 }}
                      >
                        {SENTIMENT_LABELS[sentiment.label] || sentiment.label}
                      </Tag>

                      {/* Score bar */}
                      <div style={{ margin: '16px auto 0', maxWidth: 240, height: 6, borderRadius: 3, background: 'var(--bg-input)', position: 'relative', overflow: 'hidden' }}>
                        <div style={{ width: `${((sentiment.avg_score + 1) / 2) * 100}%`, height: '100%', borderRadius: 3, background: SENTIMENT_COLORS[sentiment.label] || 'var(--text-secondary)' }} />
                      </div>

                      {/* Counts */}
                      <div style={{ display: 'flex', justifyContent: 'center', gap: 24, marginTop: 16 }}>
                        <span style={{ color: getUpColor(), fontSize: 13 }}>正面 {sentiment.positive_count}</span>
                        <span style={{ color: '#eab308', fontSize: 13 }}>中性 {sentiment.neutral_count}</span>
                        <span style={{ color: getDownColor(), fontSize: 13 }}>负面 {sentiment.negative_count}</span>
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 8 }}>
                        共 {sentiment.total_articles} 篇 · 近 {sentiment.period_days} 天
                      </div>
                    </div>
                  ) : (
                    <div style={{ textAlign: 'center', padding: 24, color: 'var(--text-tertiary)' }}>
                      <SmileOutlined style={{ fontSize: 32, marginBottom: 8, display: 'block' }} />
                      <p>暂无情绪数据</p>
                      <p style={{ fontSize: 12 }}>访问情绪仪表盘页面采集数据</p>
                    </div>
                  )}
                </Panel>
              </Col>
            </Row>
          )}

          {/* Quick Chat Button */}
          <Panel variant="minimal" style={{ marginTop: 'var(--space-4)', textAlign: 'center' }} padding="md">
            <RobotOutlined style={{ fontSize: 20, color: 'var(--accent)', marginRight: 8 }} />
            <span style={{ color: 'var(--text-secondary)', marginRight: 12 }}>想问AI关于 {code} 的分析？</span>
            <Button type="primary" icon={<RobotOutlined />} onClick={() => navigate('/chat')}>
              打开AI助手
            </Button>
          </Panel>
        </div>
      ),
    },
  ];

  return (
    <div>
      <div
        style={{
          borderBottom: '1px solid var(--border-default)',
          paddingBottom: 'var(--space-5)',
          marginBottom: 'var(--space-5)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 'var(--space-4)' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
              <h2 style={{ margin: 0, fontSize: 'var(--text-h1-size)', fontWeight: 500, letterSpacing: '-0.03em' }}>
                {etf.code} {etf.name}
              </h2>
              {etf.instrument_type && (
                <Tag color={etf.instrument_type === 'STOCK' ? 'blue' : 'purple'}>
                  {etf.instrument_type === 'STOCK' ? '个股' : 'ETF'}
                </Tag>
              )}
              {etf.market && <Tag>{etf.market}</Tag>}
            </div>
            <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-body-size)' }}>
              {etf.category || '—'}
              {etf.sector && ` | ${etf.sector}`}
              {etf.industry && ` | ${etf.industry}`}
              {etf.exchange && ` | ${etf.exchange}`}
              {etf.fund_manager && ` | ${etf.fund_manager}`}
              {etf.fund_size && ` | 规模: ${etf.fund_size >= 1e12 ? `${(etf.fund_size / 1e12).toFixed(2)}T USD` : `${(etf.fund_size / 1e8).toFixed(1)}亿`}`}
              {etf.market_cap && ` | 市值: ${etf.market_cap >= 1e12 ? `${(etf.market_cap / 1e12).toFixed(2)}T` : etf.market_cap >= 1e9 ? `${(etf.market_cap / 1e9).toFixed(1)}B` : `${(etf.market_cap / 1e6).toFixed(1)}M`} USD`}
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
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
                <div style={{ fontSize: 'var(--text-data-lg-size)', fontWeight: 400, fontFamily: 'var(--font-mono)', color: getReturnColor(indicator.return_1m, colorConvention) }}>
                  {formatPercent(indicator.return_1m)}
                </div>
                <div style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-small-size)' }}>1月收益</div>
              </div>
            )}
          </div>
        </div>
      </div>

      <Tabs items={tabItems} defaultActiveKey="kline" />
    </div>
  );
}
