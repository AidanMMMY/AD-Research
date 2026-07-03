import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Tabs, Row, Col, Statistic, Spin, Descriptions, Radio, Checkbox, Space, Alert, Button, message, Skeleton } from 'antd';
import { StarOutlined, StarFilled, RobotOutlined, ReadOutlined, SmileOutlined, StockOutlined, ArrowUpOutlined, ArrowDownOutlined, MinusOutlined } from '@ant-design/icons';
import { useStockDetail } from '@/hooks/useStocks';
import { useInstrumentScore } from '@/hooks/useScores';
import { useFavoriteStatus } from '@/hooks/useFavorites';
import { useAIHelp } from '@/hooks/useAIHelp';
import { marketApi, researchApi, stockFundamentalApi } from '@/api';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import KLineChart, { DEFAULT_OVERLAYS } from '@/components/KLineChart';
import ScoreRadar from '@/components/ScoreRadar';
import Panel from '@/components/Panel';
import PageShell from '@/components/PageShell';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import StatCard from '@/components/StatCard';
import SectionHeading from '@/components/SectionHeading';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import EmptyState from '@/components/EmptyState';
import NewsListPanel from '@/components/NewsListPanel';
import HelpTrigger from '@/components/HelpTrigger';
import HelpPopover from '@/components/HelpPopover';
import ThemeTag from '@/components/ThemeTag';
import { formatPercent } from '@/utils/format';
import { useSettingsStore } from '@/stores/settings';
import { getReturnColor } from '@/utils/color';
import { buildInstrumentDetailContext } from '@/utils/helpContext';
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

function formatMarketCap(value: number, market?: string) {
  if (market === 'A股') return `${(value / 1e8).toFixed(1)}亿 CNY`;
  if (value >= 1e12) return `${(value / 1e12).toFixed(2)}T USD`;
  if (value >= 1e9) return `${(value / 1e9).toFixed(1)}B USD`;
  return `${(value / 1e6).toFixed(1)}M USD`;
}

export default function StockDetail() {
  const { code } = useParams<{ code: string }>();
  const navigate = useNavigate();
  const { open } = useAIHelp();
  const queryClient = useQueryClient();
  const colorConvention = useSettingsStore((s) => s.colorConvention);
  const mode = useSettingsStore((s) => s.mode);
  const { data: stock, isLoading: stockLoading, error: stockError } = useStockDetail(code || '');
  const { data: score } = useInstrumentScore(code || '');
  const { isFavorite, isLoading: favLoading, toggle, isToggling } = useFavoriteStatus(code || '');
  const [timeRange, setTimeRange] = useState(120);

  const [overlays, setOverlays] = useState(() => {
    try {
      const saved = localStorage.getItem('stock-detail-overlays');
      return saved ? { ...DEFAULT_OVERLAYS, ...JSON.parse(saved) } : DEFAULT_OVERLAYS;
    } catch {
      return DEFAULT_OVERLAYS;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem('stock-detail-overlays', JSON.stringify(overlays));
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

  const { data: stockFund } = useQuery({
    queryKey: ['stock-fundamental', code],
    queryFn: () => stockFundamentalApi.get(code || '').then((r) => r.data),
    enabled: !!code,
  });

  const generateMutation = useMutation({
    mutationFn: () => researchApi.generateNote(code || ''),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-notes', code] });
      message.success('研报生成中，请稍后刷新');
    },
    onError: (err: any) => {
      message.error(err?.response?.data?.detail || '生成失败');
    },
  });

  if (stockLoading) {
    return (
      <PageShell maxWidth="wide">
        <Spin size="large" className="detail-loading" />
      </PageShell>
    );
  }
  if (stockError) {
    return (
      <PageShell maxWidth="wide">
        <Alert
          className="detail-error"
          message="加载个股详情失败"
          description={(stockError as Error).message}
          type="error"
        />
      </PageShell>
    );
  }
  if (!stock) {
    return (
      <PageShell maxWidth="wide">
        <Alert
          className="detail-error"
          message="个股不存在"
          description={`未找到代码为 ${code} 的个股`}
          type="warning"
        />
      </PageShell>
    );
  }

  const handleOpenHelp = () => {
    open({
      pageType: 'instrument_detail',
      pageTitle: `个股详情 - ${stock.name || code}`,
      contextData: buildInstrumentDetailContext(code, stock, score, indicator, sentiment, timeRange),
      quickQuestions: getQuickQuestions('instrument_detail'),
    });
  };

  const safeHistoryItems = historyData?.items || [];
  const latestNote: ResearchNote | null = researchNotes?.[0] || null;

  const metaParts = [
    stock.industry,
    stock.sector,
    stock.category,
    stock.country,
    stock.market_cap ? `市值: ${formatMarketCap(stock.market_cap, stock.market)}` : null,
  ].filter(Boolean);

  const heroStats = [
    {
      title: '1月收益',
      value: indicator?.return_1m,
      suffix: '%',
      color: (indicator?.return_1m ?? 0) >= 0 ? 'detail-kpi-rise' : 'detail-kpi-fall',
    },
    { title: 'RSI14', value: indicator?.rsi14, suffix: undefined, color: 'detail-kpi-accent' },
    { title: '波动率20日', value: indicator?.volatility_20d, suffix: '%', color: undefined },
    { title: '最大回撤', value: indicator?.max_drawdown_1y, suffix: '%', color: 'detail-kpi-fall' },
  ];

  const formatSigned = (v?: number | null) => {
    if (v == null) return '—';
    return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`;
  };

  const tabItems = [
    {
      key: 'kline',
      label: 'K线行情',
      children: (
        <Panel title="K线行情" padding="md" extra={<HelpTrigger tooltip="AI 解释K线" onClick={handleOpenHelp} />}>
          <div className="detail-toolbar">
            <Space size="large" wrap>
              <Space>
                <HelpPopover termKey="time_range" mode={mode}>时间范围</HelpPopover>：
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
                      <HelpPopover termKey={INDICATOR_OPTION_TERMS[opt.value]} mode={mode}>{opt.label}</HelpPopover>
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
              <Alert className="detail-chart__empty" message="暂无历史行情数据" type="info" showIcon />
            )
          )}
        </Panel>
      ),
    },
    {
      key: 'indicators',
      label: '指标数据',
      children: (
        <Panel title="指标数据" padding="md" extra={<HelpTrigger tooltip="AI 解释技术指标" onClick={handleOpenHelp} />}>
          <div className="detail-indicator-grid">
            {[
              { title: <HelpPopover termKey="rsi14" mode={mode}>RSI14</HelpPopover>, value: indicator?.rsi14, precision: 1 },
              { title: <HelpPopover termKey="sharpe_1y" mode={mode}>夏普1年</HelpPopover>, value: indicator?.sharpe_1y, precision: 2 },
              { title: <HelpPopover termKey="volatility_20d" mode={mode}>波动率20日</HelpPopover>, value: indicator?.volatility_20d, precision: 2, suffix: '%' },
              { title: <HelpPopover termKey="max_drawdown_1y" mode={mode}>最大回撤</HelpPopover>, value: indicator?.max_drawdown_1y, precision: 2, suffix: '%' },
              { title: <HelpPopover termKey="return_1m" mode={mode}>1月收益</HelpPopover>, value: indicator?.return_1m, precision: 2, suffix: '%' },
              { title: <HelpPopover termKey="return_3m" mode={mode}>3月收益</HelpPopover>, value: indicator?.return_3m, precision: 2, suffix: '%' },
              { title: <HelpPopover termKey="return_1y" mode={mode}>1年收益</HelpPopover>, value: indicator?.return_1y, precision: 2, suffix: '%' },
              { title: <HelpPopover termKey="ma5" mode={mode}>MA5</HelpPopover>, value: indicator?.ma5, precision: 2 },
            ].map((m, i) => (
              <div key={i} className="detail-indicator-item">
                <Statistic title={m.title} value={m.value} precision={m.precision} suffix={m.suffix} />
              </div>
            ))}
          </div>
        </Panel>
      ),
    },
    {
      key: 'score',
      label: '综合评分',
      children: score ? (
        <Panel title="综合评分" padding="md" extra={<HelpTrigger tooltip="AI 解释评分维度" onClick={handleOpenHelp} />}>
          <Row gutter={[16, 16]}>
            <Col xs={24} md={12}>
              <ScoreRadar data={score} />
            </Col>
            <Col xs={24} md={12}>
              <Panel variant="minimal" title="评分详情" padding="md">
                <Descriptions column={1}>
                  <Descriptions.Item label={<HelpPopover termKey="composite_score" mode={mode}>综合评分</HelpPopover>}>{score.composite_score}</Descriptions.Item>
                  <Descriptions.Item label={<HelpPopover termKey="rank_overall" mode={mode}>全市场排名</HelpPopover>}>{score.rank_overall}</Descriptions.Item>
                  <Descriptions.Item label={<HelpPopover termKey="rank_category" mode={mode}>分类排名</HelpPopover>}>{score.rank_category}</Descriptions.Item>
                  <Descriptions.Item label={<HelpPopover termKey="score_return" mode={mode}>收益得分</HelpPopover>}>{score.score_return}</Descriptions.Item>
                  <Descriptions.Item label={<HelpPopover termKey="score_risk" mode={mode}>风险得分</HelpPopover>}>{score.score_risk}</Descriptions.Item>
                  <Descriptions.Item label={<HelpPopover termKey="score_sharpe" mode={mode}>夏普得分</HelpPopover>}>{score.score_sharpe}</Descriptions.Item>
                  <Descriptions.Item label={<HelpPopover termKey="score_liquidity" mode={mode}>流动性得分</HelpPopover>}>{score.score_liquidity}</Descriptions.Item>
                  <Descriptions.Item label={<HelpPopover termKey="score_trend" mode={mode}>趋势得分</HelpPopover>}>{score.score_trend}</Descriptions.Item>
                </Descriptions>
              </Panel>
            </Col>
          </Row>
        </Panel>
      ) : (
        <Panel title="综合评分" padding="md">
          <EmptyState
            title="暂无评分数据"
            description="该个股尚未生成综合评分，可稍后再来查看"
          />
        </Panel>
      ),
    },
    {
      key: 'ai',
      label: (
        <span>
          <RobotOutlined className="detail-tab-icon" />
          AI分析
        </span>
      ),
      children: (
        <div className="detail-tab-panel">
          {notesLoading || sentimentLoading ? (
            <Panel title="AI分析" padding="md">
              <Skeleton active paragraph={{ rows: 8 }} />
            </Panel>
          ) : (
            <Row gutter={[16, 16]}>
              <Col xs={24} md={12}>
                <Panel
                  variant="default"
                  title={
                    <span>
                      <ReadOutlined className="detail-tab-icon detail-tab-icon--lg" />
                      <HelpPopover termKey="ai_research_note" mode={mode}>AI 研究笔记</HelpPopover>
                    </span>
                  }
                  extra={
                    <Button
                      size="small"
                      type="primary"
                      icon={<RobotOutlined />}
                      loading={generateMutation.isPending}
                      disabled={generateMutation.isPending}
                      onClick={() => generateMutation.mutate()}
                    >
                      生成研报
                    </Button>
                  }
                  padding="md"
                >
                  {latestNote ? (
                    <div>
                      <div className="ai-note-meta">
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
                          <span className="ai-note-confidence">
                            置信度 {latestNote.confidence}/10
                          </span>
                        )}
                        <span className="ai-note-time">
                          {latestNote.generated_at?.slice(0, 16) || latestNote.created_at?.slice(0, 16)}
                        </span>
                      </div>
                      <p className="ai-note-summary">{latestNote.summary}</p>
                      <Button
                        type="link"
                        size="small"
                        onClick={() => navigate(`/research`)}
                        className="detail-link-button"
                      >
                        查看全部研报 →
                      </Button>
                    </div>
                  ) : (
                    <div className="ai-empty">
                      <RobotOutlined className="ai-empty__icon" />
                      <p>暂无AI研报</p>
                      <p className="ai-empty__hint">点击上方"生成研报"按钮开始分析</p>
                    </div>
                  )}
                </Panel>
              </Col>

              <Col xs={24} md={12}>
                <Panel
                  variant="default"
                  title={
                    <span>
                      <SmileOutlined className="detail-tab-icon detail-tab-icon--lg" />
                      <HelpPopover termKey="market_sentiment" mode={mode}>市场情绪</HelpPopover>
                    </span>
                  }
                  padding="md"
                >
                  {sentiment ? (
                    <div className="ai-empty">
                      <div
                        className="sentiment-score"
                        style={{ color: SENTIMENT_COLORS[sentiment.label] || 'var(--text-secondary)' }}
                      >
                        {sentiment.avg_score?.toFixed(2) ?? '—'}
                      </div>
                      <ThemeTag
                        variant={
                          sentiment.label === 'bullish' || sentiment.label === 'positive'
                            ? 'rise'
                            : sentiment.label === 'bearish' || sentiment.label === 'negative'
                              ? 'fall'
                              : 'neutral'
                        }
                        className="sentiment-tag"
                      >
                        {SENTIMENT_LABELS[sentiment.label] || sentiment.label}
                      </ThemeTag>

                      <div className="sentiment-bar">
                        <div
                          className="sentiment-bar__fill"
                          style={{
                            width: `${((sentiment.avg_score + 1) / 2) * 100}%`,
                            background: SENTIMENT_COLORS[sentiment.label] || 'var(--text-secondary)',
                          }}
                        />
                      </div>

                      <div className="sentiment-counts">
                        <span className="sentiment-counts__item sentiment-counts__item--positive tabular-nums">正面 {sentiment.positive_count}</span>
                        <span className="sentiment-counts__item sentiment-counts__item--neutral tabular-nums">中性 {sentiment.neutral_count}</span>
                        <span className="sentiment-counts__item sentiment-counts__item--negative tabular-nums">负面 {sentiment.negative_count}</span>
                      </div>
                      <div className="sentiment-meta">
                        共 {sentiment.total_articles} 篇 · 近 {sentiment.period_days} 天
                      </div>
                    </div>
                  ) : (
                    <div className="ai-empty">
                      <SmileOutlined className="ai-empty__icon" />
                      <p>暂无情绪数据</p>
                      <p className="ai-empty__hint">访问情绪仪表盘页面采集数据</p>
                    </div>
                  )}
                </Panel>
              </Col>
            </Row>
          )}

          <Panel variant="default" className="ai-assistant-cta" padding="md">
            <RobotOutlined className="ai-assistant-cta__icon" />
            <span className="ai-assistant-cta__text">想问AI关于 {code} 的分析？</span>
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
          <ReadOutlined className="detail-tab-icon" />
          相关新闻
        </span>
      ),
      children: (
        <Panel title="相关新闻" padding="md">
          <NewsListPanel symbol={code || ''} limit={15} bare />
        </Panel>
      ),
    },
    {
      key: 'valuation',
      label: '估值数据',
      children: (
        <Panel title="估值数据" padding="md">
          {!stockFund ? (
            <Skeleton active paragraph={{ rows: 4 }} />
          ) : (
            <div>
              <div className="valuation-grid">
                {[
                  { title: 'PE (TTM)', termKey: 'pe_ttm', value: stockFund.pe_ttm, suffix: '倍', precision: 2 },
                  { title: 'PB', termKey: 'pb', value: stockFund.pb, suffix: '倍', precision: 2 },
                  { title: '总市值', termKey: 'total_mv', value: stockFund.total_mv ? (stockFund.total_mv / 10000).toFixed(2) : undefined, suffix: '亿 CNY' },
                  { title: '流通市值', termKey: 'circ_mv', value: stockFund.circ_mv ? (stockFund.circ_mv / 10000).toFixed(2) : undefined, suffix: '亿 CNY' },
                  { title: '换手率（自由流通）', termKey: 'turnover_rate_f', value: stockFund.turnover_rate_f, suffix: '%', precision: 2 },
                  { title: '量比', termKey: 'volume_ratio', value: stockFund.volume_ratio, precision: 2 },
                  stockFund.eps != null ? { title: 'EPS（最新财报）', termKey: 'eps', value: stockFund.eps, suffix: '元', precision: 2 } : null,
                  stockFund.roe != null ? { title: 'ROE（最新财报）', termKey: 'roe', value: stockFund.roe, suffix: '%', precision: 2 } : null,
                  stockFund.revenue_yoy != null ? { title: '营收 YoY', termKey: 'revenue_yoy', value: stockFund.revenue_yoy, suffix: '%', precision: 2 } : null,
                  stockFund.grossprofit_margin != null ? { title: '毛利率', termKey: 'grossprofit_margin', value: stockFund.grossprofit_margin, suffix: '%', precision: 2 } : null,
                ].filter(Boolean).map((m: any) => (
                  <div key={m.title} className="valuation-cell">
                    <div className="valuation-cell__label">
                      {m.termKey ? (
                        <HelpPopover termKey={m.termKey} mode={mode}>{m.title}</HelpPopover>
                      ) : m.title}
                    </div>
                    <div className="valuation-cell__value tabular-nums">
                      {m.value !== undefined && m.value !== null ? (
                        <>
                          {typeof m.value === 'number' && m.precision !== undefined
                            ? m.value.toFixed(m.precision)
                            : m.value}
                          {m.suffix && <span className="valuation-cell__suffix">{m.suffix}</span>}
                        </>
                      ) : (
                        <span className="valuation-cell__empty">—</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              <Alert
                type="info"
                message="数据来源：Tushare Pro"
                description={`估值日期：${stockFund.trade_date || '未知'}。基本面数据（EPS/ROE/毛利率等）需运行财报采集管道后获取。`}
                className="valuation-alert"
              />
            </div>
          )}
        </Panel>
      ),
    },
  ];

  return (
    <PageShell maxWidth="wide">
      <div className="detail-hero">
        <div className="detail-hero__row">
          <div>
            <div className="detail-hero__title">
              <StockOutlined className="detail-hero__icon" />
              <InstrumentCodeTag code={stock.code} name={stock.name} name_zh={stock.name_zh} />
              <h1 className="detail-hero__title-text">{stock.name}</h1>
              <ThemeTag variant="accent">个股</ThemeTag>
              {stock.market && <ThemeTag>{stock.market}</ThemeTag>}
              {stock.exchange && <ThemeTag>{stock.exchange}</ThemeTag>}
            </div>
            <div className="detail-hero__meta">
              {metaParts.join(' | ') || '—'}
            </div>
          </div>
          <div className="detail-hero__actions">
            <Button
              type={isFavorite ? 'primary' : 'default'}
              icon={isFavorite ? <StarFilled /> : <StarOutlined />}
              loading={isToggling || favLoading}
              onClick={handleToggleFavorite}
            >
              {isFavorite ? '已收藏' : '收藏'}
            </Button>
            {indicator?.return_1m !== undefined && (
              <div className="detail-hero__kpi">
                <div
                  className="detail-hero__kpi-value detail-hero__kpi-value--signed tabular-nums"
                  style={{ color: getReturnColor(indicator.return_1m, colorConvention) }}
                >
                  {indicator.return_1m > 0 ? (
                    <ArrowUpOutlined className="detail-arrow-icon" aria-label="up" />
                  ) : indicator.return_1m < 0 ? (
                    <ArrowDownOutlined className="detail-arrow-icon" aria-label="down" />
                  ) : (
                    <MinusOutlined className="detail-arrow-icon" aria-label="flat" />
                  )}
                  {formatPercent(indicator.return_1m)}
                </div>
                <div className="detail-hero__kpi-label">1月收益</div>
              </div>
            )}
          </div>
        </div>
      </div>

      <SectionHeading title="核心指标" />
      <ResponsiveGrid cols={4} gap="md" className="detail-section">
        {heroStats.map((stat) => (
          <div key={stat.title} className={stat.color}>
            <StatCard
              title={stat.title}
              value={stat.value != null ? formatSigned(stat.value) : '—'}
              suffix={stat.suffix}
            />
          </div>
        ))}
      </ResponsiveGrid>

      <Tabs items={tabItems} defaultActiveKey="kline" />
    </PageShell>
  );
}
