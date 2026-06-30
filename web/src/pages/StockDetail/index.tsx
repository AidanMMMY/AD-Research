import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Tabs, Row, Col, Statistic, Spin, Descriptions, Radio, Checkbox, Space, Alert, Button, message, Skeleton } from 'antd';
import { StarOutlined, StarFilled, RobotOutlined, ReadOutlined, SmileOutlined, StockOutlined } from '@ant-design/icons';
import { useStockDetail } from '@/hooks/useStocks';
import { useETFScore } from '@/hooks/useScores';
import { useFavoriteStatus } from '@/hooks/useFavorites';
import { useAIHelp } from '@/hooks/useAIHelp';
import { marketApi, researchApi, stockFundamentalApi } from '@/api';
import { useQuery } from '@tanstack/react-query';
import KLineChart, { DEFAULT_OVERLAYS } from '@/components/KLineChart';
import ScoreRadar from '@/components/ScoreRadar';
import Panel from '@/components/Panel';
import NewsListPanel from '@/components/NewsListPanel';
import HelpTrigger from '@/components/HelpTrigger';
import HelpPopover from '@/components/HelpPopover';
import ThemeTag from '@/components/ThemeTag';
import { formatPercent } from '@/utils/format';
import { useSettingsStore } from '@/stores/settings';
import { getReturnColor } from '@/utils/color';
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
  bullish: 'var(--color-rise)',
  positive: 'var(--color-rise)',
  bearish: 'var(--color-fall)',
  negative: 'var(--color-fall)',
  neutral: 'var(--text-tertiary)',
};

const SENTIMENT_LABELS: Record<string, string> = {
  bullish: '看多',
  positive: '看多',
  bearish: '看空',
  negative: '看空',
  neutral: '中性',
};

export default function StockDetail() {
  const { code } = useParams<{ code: string }>();
  const navigate = useNavigate();
  const { open } = useAIHelp();
  const colorConvention = useSettingsStore((s) => s.colorConvention);
  const { data: stock, isLoading: stockLoading, error: stockError } = useStockDetail(code || '');
  const { data: score } = useETFScore(code || '');
  const { isFavorite, isLoading: favLoading, toggle, isToggling } = useFavoriteStatus(code || '');
  const [timeRange, setTimeRange] = useState(120);

  // Persist K-line overlay preferences in localStorage (shared key with ETF)
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
    queryKey: ['stock-history', code, timeRange],
    queryFn: () => marketApi.history(code || '', { limit: timeRange }).then((r) => r.data),
    enabled: !!code,
    retry: 1,
  });

  const { data: indicator } = useQuery({
    queryKey: ['stock-indicator', code],
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

  // A-share stock fundamentals (PE/PB/market cap etc.)
  const { data: stockFund } = useQuery({
    queryKey: ['stock-fundamental', code],
    queryFn: () => stockFundamentalApi.get(code || '').then((r) => r.data),
    enabled: !!code,
  });

  if (stockLoading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (stockError) return <Alert message="加载个股详情失败" description={(stockError as Error).message} type="error" style={{ margin: 'var(--space-6)' }} />;
  if (!stock) return <Alert message="个股不存在" description={`未找到代码为 ${code} 的个股`} type="warning" style={{ margin: 'var(--space-6)' }} />;

  const handleOpenHelp = () => {
    open({
      pageType: 'etf_detail',
      pageTitle: `个股详情 - ${stock.name || code}`,
      contextData: buildETFDetailContext(code, stock, score, indicator, sentiment, timeRange),
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
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 'var(--space-3)' }}>
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
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 'var(--space-3)' }}>
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
          <RobotOutlined style={{ marginRight: 'var(--space-1)' }} />
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
                  title={<span><ReadOutlined style={{ marginRight: 'var(--space-1-5)' }} /><HelpPopover termKey="ai_research_note">AI 研究笔记</HelpPopover></span>}
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
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 'var(--space-2)' }}>
                        {latestNote.sentiment && (
                          <ThemeTag
                            variant={
                              latestNote.sentiment === 'bullish' || latestNote.sentiment === 'positive'
                                ? 'rise'
                                : latestNote.sentiment === 'bearish' || latestNote.sentiment === 'negative'
                                  ? 'fall'
                                  : 'neutral'
                            }
                          >
                            {SENTIMENT_LABELS[latestNote.sentiment] || latestNote.sentiment}
                          </ThemeTag>
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
                    <div style={{ textAlign: 'center', padding: 'var(--space-6)', color: 'var(--text-tertiary)' }}>
                      <RobotOutlined style={{ fontSize: 32, marginBottom: 'var(--space-2)', display: 'block' }} />
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
                  title={<span><SmileOutlined style={{ marginRight: 'var(--space-1-5)' }} /><HelpPopover termKey="market_sentiment">市场情绪</HelpPopover></span>}
                  padding="md"
                >
                  {sentiment ? (
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: 48, fontWeight: 700, color: SENTIMENT_COLORS[sentiment.label] || 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                        {sentiment.avg_score.toFixed(2)}
                      </div>
                      <ThemeTag
                        variant={
                          sentiment.label === 'bullish' || sentiment.label === 'positive'
                            ? 'rise'
                            : sentiment.label === 'bearish' || sentiment.label === 'negative'
                              ? 'fall'
                              : 'neutral'
                        }
                        style={{ fontSize: 13, padding: '2px 12px', marginTop: 4 }}
                      >
                        {SENTIMENT_LABELS[sentiment.label] || sentiment.label}
                      </ThemeTag>

                      <div style={{ margin: 'var(--space-4) auto 0', maxWidth: 240, height: 6, borderRadius: 3, background: 'var(--bg-input)', position: 'relative', overflow: 'hidden' }}>
                        <div style={{ width: `${((sentiment.avg_score + 1) / 2) * 100}%`, height: '100%', borderRadius: 3, background: SENTIMENT_COLORS[sentiment.label] || 'var(--text-secondary)' }} />
                      </div>

                      <div style={{ display: 'flex', justifyContent: 'center', gap: 24, marginTop: 'var(--space-4)' }}>
                        <span style={{ color: 'var(--color-rise)', fontSize: 13 }}>正面 {sentiment.positive_count}</span>
                        <span style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>中性 {sentiment.neutral_count}</span>
                        <span style={{ color: 'var(--color-fall)', fontSize: 13 }}>负面 {sentiment.negative_count}</span>
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 'var(--space-2)' }}>
                        共 {sentiment.total_articles} 篇 · 近 {sentiment.period_days} 天
                      </div>
                    </div>
                  ) : (
                    <div style={{ textAlign: 'center', padding: 'var(--space-6)', color: 'var(--text-tertiary)' }}>
                      <SmileOutlined style={{ fontSize: 32, marginBottom: 'var(--space-2)', display: 'block' }} />
                      <p>暂无情绪数据</p>
                      <p style={{ fontSize: 12 }}>访问情绪仪表盘页面采集数据</p>
                    </div>
                  )}
                </Panel>
              </Col>
            </Row>
          )}

          <Panel variant="minimal" style={{ marginTop: 'var(--space-4)', textAlign: 'center' }} padding="md">
            <RobotOutlined style={{ fontSize: 20, color: 'var(--accent)', marginRight: 'var(--space-2)' }} />
            <span style={{ color: 'var(--text-secondary)', marginRight: 'var(--space-3)' }}>想问AI关于 {code} 的分析？</span>
            <Button type="primary" icon={<RobotOutlined />} onClick={() => navigate('/chat')}>
              打开AI助手
            </Button>
          </Panel>
        </div>
      ),
    },
    {
      key: 'news',
      label: (
        <span>
          <ReadOutlined style={{ marginRight: 'var(--space-1)' }} />
          相关新闻
        </span>
      ),
      children: <NewsListPanel symbol={code || ''} limit={15} bare />,
    },
    {
      key: 'valuation',
      label: '估值数据',
      children: (
        <div>
          {!stockFund ? (
            <Skeleton active paragraph={{ rows: 4 }} />
          ) : (
            <div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(3, 1fr)',
                  borderTop: '1px solid var(--border-default)',
                  borderBottom: '1px solid var(--border-default)',
                }}
              >
                {[
                  { title: 'PE (TTM)', value: stockFund.pe_ttm, suffix: '倍', precision: 2 },
                  { title: 'PB', value: stockFund.pb, suffix: '倍', precision: 2 },
                  { title: '总市值', value: stockFund.total_mv ? (stockFund.total_mv / 10000).toFixed(2) : undefined, suffix: '亿 CNY' },
                  { title: '流通市值', value: stockFund.circ_mv ? (stockFund.circ_mv / 10000).toFixed(2) : undefined, suffix: '亿 CNY' },
                  { title: '换手率（自由流通）', value: stockFund.turnover_rate_f, suffix: '%', precision: 2 },
                  { title: '量比', value: stockFund.volume_ratio, precision: 2 },
                  stockFund.eps != null ? { title: 'EPS（最新财报）', value: stockFund.eps, suffix: '元', precision: 2 } : null,
                  stockFund.roe != null ? { title: 'ROE（最新财报）', value: stockFund.roe, suffix: '%', precision: 2 } : null,
                  stockFund.revenue_yoy != null ? { title: '营收 YoY', value: stockFund.revenue_yoy, suffix: '%', precision: 2 } : null,
                  stockFund.grossprofit_margin != null ? { title: '毛利率', value: stockFund.grossprofit_margin, suffix: '%', precision: 2 } : null,
                ].filter(Boolean).map((m: any, i, arr) => {
                  const isLastRow = i >= arr.length - (arr.length % 3 || 3);
                  const hasRightBorder = (i + 1) % 3 !== 0;
                  return (
                    <div
                      key={m.title}
                      style={{
                        padding: '20px 16px',
                        borderRight: hasRightBorder ? '1px solid var(--border-default)' : 'none',
                        borderBottom: isLastRow ? 'none' : '1px solid var(--border-default)',
                      }}
                    >
                      <div
                        style={{
                          fontSize: 'var(--text-label-size)',
                          color: 'var(--text-tertiary)',
                          fontWeight: 500,
                          marginBottom: '12px',
                          letterSpacing: '0.12em',
                          textTransform: 'uppercase',
                        }}
                      >
                        {m.title}
                      </div>
                      <div
                        style={{
                          fontSize: 'var(--text-data-lg-size)',
                          fontWeight: 400,
                          color: 'var(--text-primary)',
                          fontFamily: 'var(--font-mono)',
                          lineHeight: 1.2,
                        }}
                      >
                        {m.value !== undefined && m.value !== null ? (
                          <>
                            {typeof m.value === 'number' && m.precision !== undefined
                              ? m.value.toFixed(m.precision)
                              : m.value}
                            {m.suffix && <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)', marginLeft: 4 }}>{m.suffix}</span>}
                          </>
                        ) : (
                          <span style={{ color: 'var(--text-tertiary)' }}>—</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
              <Alert
                type="info"
                message="数据来源：Tushare Pro"
                description={`估值日期：${stockFund.trade_date}。基本面数据（EPS/ROE/毛利率等）需运行财报采集管道后获取。`}
                style={{ marginTop: 'var(--space-4)' }}
              />
            </div>
          )}
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
              <StockOutlined style={{ fontSize: 22, color: 'var(--accent)' }} />
              <h2 style={{ margin: 0, fontSize: 'var(--text-h1-size)', fontWeight: 500, letterSpacing: '-0.03em' }}>
                {stock.code} {stock.name}
              </h2>
              <ThemeTag variant="accent">个股</ThemeTag>
              {stock.market && <ThemeTag>{stock.market}</ThemeTag>}
              {stock.exchange && <ThemeTag>{stock.exchange}</ThemeTag>}
            </div>
            <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-body-size)' }}>
              {stock.industry || '—'}
              {stock.sector && ` | ${stock.sector}`}
              {stock.category && ` | ${stock.category}`}
              {stock.country && ` | ${stock.country}`}
              {stock.market_cap && (
                stock.market === 'A股'
                  ? ` | 市值: ${(stock.market_cap / 1e8).toFixed(1)}亿 CNY`
                  : ` | 市值: ${stock.market_cap >= 1e12 ? `${(stock.market_cap / 1e12).toFixed(2)}T` : stock.market_cap >= 1e9 ? `${(stock.market_cap / 1e9).toFixed(1)}B` : `${(stock.market_cap / 1e6).toFixed(1)}M`} USD`
              )}
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
