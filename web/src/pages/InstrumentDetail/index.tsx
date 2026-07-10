import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import './styles.css';
import { Row, Col, Statistic, Spin, Descriptions, Radio, Checkbox, Space, Alert, Button, message, Skeleton } from 'antd';
import { StarOutlined, StarFilled, RobotOutlined, ReadOutlined, SmileOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { useInstrumentDetail } from '@/hooks/useInstrumentList';
import { useInstrumentScore } from '@/hooks/useScores';
import { useFavoriteStatus } from '@/hooks/useFavorites';
import { useAIHelp } from '@/hooks/useAIHelp';
import { marketApi, researchApi } from '@/api';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import KLineChart, { DEFAULT_OVERLAYS } from '@/components/KLineChart';
import ScoreRadar from '@/components/ScoreRadar';
import Panel from '@/components/Panel';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import StatCard from '@/components/StatCard';
import SectionHeading from '@/components/SectionHeading';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import EmptyState from '@/components/EmptyState';
import NewsListPanel from '@/components/NewsListPanel';
import HelpTrigger from '@/components/HelpTrigger';
import HelpPopover from '@/components/HelpPopover';
import ThemeTag from '@/components/ThemeTag';
import LoadingBlock from '@/components/LoadingBlock';
import TypeAwareModules from '@/components/TypeAwareModules';
import { formatPercent } from '@/utils/format';
import { useSettingsStore } from '@/stores/settings';
import { getReturnColor } from '@/utils/color';
import { buildInstrumentDetailContext } from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';
import { SENTIMENT_COLORS, SENTIMENT_LABELS } from '@/utils/sentiment';
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

const INSTRUMENT_TYPE_LABELS: Record<string, string> = {
  STOCK: '个股',
  CRYPTO: '数字货币',
  ETF: 'ETF',
};

/**
 * Map A-share board names to a ThemeTag variant so the badge colour
 * reflects the board's risk profile (科创板/创业板/北交所 are highlighted).
 */
const BOARD_VARIANT: Record<string, 'default' | 'accent' | 'success' | 'warning' | 'error'> = {
  主板: 'default',
  创业板: 'accent',
  科创板: 'accent',
  北交所: 'warning',
};

function formatFundSize(value: number, market?: string) {
  if (market === 'US') {
    if (value >= 1e12) return `${(value / 1e12).toFixed(2)}T USD`;
    if (value >= 1e9) return `${(value / 1e9).toFixed(1)}B USD`;
    return `${(value / 1e6).toFixed(1)}M USD`;
  }
  return `${(value / 1e8).toFixed(1)}亿`;
}

function formatMarketCap(value: number, market?: string) {
  if (market === 'A股') return `${(value / 1e8).toFixed(1)}亿 CNY`;
  if (value >= 1e12) return `${(value / 1e12).toFixed(2)}T USD`;
  if (value >= 1e9) return `${(value / 1e9).toFixed(1)}B USD`;
  return `${(value / 1e6).toFixed(1)}M USD`;
}

export default function InstrumentDetail() {
  const { code } = useParams<{ code: string }>();
  const navigate = useNavigate();
  const { open } = useAIHelp();
  const queryClient = useQueryClient();
  const colorConvention = useSettingsStore((s) => s.colorConvention);
  const mode = useSettingsStore((s) => s.mode);
  const { data: instrument, isLoading: instrumentLoading, error: instrumentError } = useInstrumentDetail(code || '');
  const { data: score } = useInstrumentScore(code || '');
  const { isFavorite, isLoading: favLoading, toggle, isToggling } = useFavoriteStatus(code || '');
  const [timeRange, setTimeRange] = useState(120);
  const [adjusted, setAdjusted] = useState(true);

  const [overlays, setOverlays] = useState(() => {
    try {
      const saved = localStorage.getItem('instrument-detail-overlays');
      return saved ? { ...DEFAULT_OVERLAYS, ...JSON.parse(saved) } : DEFAULT_OVERLAYS;
    } catch {
      return DEFAULT_OVERLAYS;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem('instrument-detail-overlays', JSON.stringify(overlays));
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
    queryKey: ['instrument-history', code, timeRange, adjusted],
    queryFn: () => marketApi.history(code || '', { limit: timeRange, adjusted }).then((r) => r.data),
    enabled: !!code,
    retry: 1,
  });

  const { data: indicator } = useQuery({
    queryKey: ['instrument-indicator', code],
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

  if (instrumentLoading) {
    return (
      <PageShell maxWidth="wide">
        <LoadingBlock size="lg" label="加载中…" />
      </PageShell>
    );
  }
  if (instrumentError) {
    return (
      <PageShell maxWidth="wide">
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/instruments')}
          className="ad-mb-3"
        >
          返回标的列表
        </Button>
        <Alert
          className="detail-error"
          message="加载标的详情失败"
          description={(instrumentError as Error).message}
          type="error"
        />
      </PageShell>
    );
  }
  if (!instrument) {
    return (
      <PageShell maxWidth="wide">
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/instruments')}
          className="ad-mb-3"
        >
          返回标的列表
        </Button>
        <Alert
          className="detail-error"
          message="标的不存在"
          description={`未找到代码为 ${code} 的标的`}
          type="warning"
        />
      </PageShell>
    );
  }

  const handleOpenHelp = () => {
    open({
      pageType: 'instrument_detail',
      pageTitle: `标的详情 - ${instrument.name || code}`,
      contextData: buildInstrumentDetailContext(code, instrument, score, indicator, sentiment, timeRange),
      quickQuestions: getQuickQuestions('instrument_detail'),
    });
  };

  const safeHistoryItems = historyData?.items || [];
  const latestNote: ResearchNote | null = researchNotes?.[0] || null;

  const metaParts = [
    instrument.category,
    instrument.sector,
    instrument.industry,
    instrument.exchange,
    instrument.fund_manager,
    instrument.fund_size ? `规模: ${formatFundSize(instrument.fund_size, instrument.market)}` : null,
    instrument.market_cap ? `市值: ${formatMarketCap(instrument.market_cap, instrument.market)}` : null,
  ].filter(Boolean);

  const heroStats = [
    {
      title: '1月收益',
      value: indicator?.return_1m,
      suffix: '%',
      color: (indicator?.return_1m ?? 0) >= 0 ? 'detail-kpi-rise' : 'detail-kpi-fall',
      term: 'return_1m',
    },
    { title: 'RSI14', value: indicator?.rsi14, suffix: undefined, color: 'detail-kpi-accent', term: 'rsi14' },
    { title: '波动率20日', value: indicator?.volatility_20d, suffix: '%', color: undefined, term: 'volatility_20d' },
    { title: '最大回撤', value: indicator?.max_drawdown_1y, suffix: '%', color: 'detail-kpi-fall', term: 'max_drawdown_1y' },
  ];

  const formatSigned = (v?: number | null) => {
    if (v == null) return '—';
    return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`;
  };

  return (
    <PageShell maxWidth="wide">
      <Button
        type="text"
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/instruments')}
        className="ad-mb-3"
      >
        返回标的列表
      </Button>
      <PageHeader
        eyebrow="标的详情"
        title={instrument.name}
        description={metaParts.join(' · ') || '—'}
        extra={
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
                  className="detail-hero__kpi-value tabular-nums"
                  style={{ color: getReturnColor(indicator.return_1m, colorConvention) }}
                >
                  {formatPercent(indicator.return_1m)}
                </div>
                <div className="detail-hero__kpi-label">1月收益</div>
              </div>
            )}
          </div>
        }
      />

      <div className="detail-hero">
        <InstrumentCodeTag code={instrument.code} name={instrument.name} name_zh={instrument.name_zh} />
        {instrument.instrument_type && (
          <ThemeTag variant={instrument.instrument_type === 'ETF' ? 'default' : 'accent'}>
            {INSTRUMENT_TYPE_LABELS[instrument.instrument_type] || instrument.instrument_type}
          </ThemeTag>
        )}
        {instrument.market && <ThemeTag>{instrument.market}</ThemeTag>}
        {instrument.listing_market && (
          <ThemeTag title={`上市市场: ${instrument.listing_market}`}>
            {instrument.listing_market}
          </ThemeTag>
        )}
        {instrument.board && (
          <ThemeTag
            variant={BOARD_VARIANT[instrument.board] || 'default'}
            title={`所属板块: ${instrument.board}`}
          >
            {instrument.board}
          </ThemeTag>
        )}
        {instrument.status && (
          <ThemeTag
            variant={
              instrument.status === 'active' || instrument.status === 'listed'
                ? 'success'
                : instrument.status === 'suspended'
                  ? 'warning'
                  : 'error'
            }
            title={`状态: ${instrument.status}`}
          >
            {instrument.status === 'active' || instrument.status === 'listed'
              ? '上市'
              : instrument.status === 'suspended'
                ? '停牌'
                : instrument.status === 'delisted'
                  ? '退市'
                  : instrument.status}
          </ThemeTag>
        )}
      </div>

      {/* ─── 1) K-line + controls (full width) ──────────────────────── */}
      <Panel
        className="detail-section"
        title="K线行情"
        padding="md"
        extra={<HelpTrigger tooltip="AI 解释K线" onClick={handleOpenHelp} />}
      >
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
            <Space>
              <span>复权：</span>
              <Radio.Group
                value={adjusted}
                onChange={(e) => setAdjusted(e.target.value)}
                optionType="button"
                buttonStyle="solid"
                size="small"
              >
                <Radio.Button value={false}>不复权</Radio.Button>
                <Radio.Button value={true}>前复权</Radio.Button>
              </Radio.Group>
            </Space>
          </Space>
        </div>
        {historyLoading ? <Spin /> : (
          safeHistoryItems.length ? (
            <KLineChart data={safeHistoryItems} overlays={overlays} adjusted={adjusted} />
          ) : (
            <Alert className="detail-chart__empty" message="暂无历史行情数据" type="info" showIcon />
          )
        )}
      </Panel>

      {/* ─── 2) Key statistics (directly below K-line) ──────────────── */}
      <SectionHeading title="关键数据" />
      <ResponsiveGrid cols={4} gap="md" className="detail-section">
        {heroStats.map((stat) => (
          <div key={stat.title} className={stat.color}>
            <StatCard
              title={stat.title}
              value={stat.value != null ? formatSigned(stat.value) : '—'}
              suffix={stat.suffix}
              term={stat.term}
            />
          </div>
        ))}
      </ResponsiveGrid>

      {/* ─── 3) Indicators compact panel ────────────────────────────── */}
      <SectionHeading title="技术指标" />
      <Panel
        className="detail-section"
        title="技术指标"
        padding="md"
        extra={<HelpTrigger tooltip="AI 解释技术指标" onClick={handleOpenHelp} />}
      >
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

      {/* ─── 4) Type-aware module (ETF holdings / STOCK fundamentals / CRYPTO market-data) ─── */}
      {/* Branches on `instrument.instrument_type` internally. See
          `components/TypeAwareModules.tsx` and the `getInstrumentModuleKind`
          helper for the routing rules. */}
      <div className="detail-section">
        <TypeAwareModules instrument={instrument} />
      </div>

      {/* ─── 5) 综合评分 ──────────────────────────────────────────── */}
      <Panel
        className="detail-section"
        title="综合评分"
        padding="md"
        extra={<HelpTrigger tooltip="AI 解释评分维度" onClick={handleOpenHelp} />}
      >
        {score ? (
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
        ) : (
          <EmptyState
            title="暂无评分数据"
            description="该标的尚未生成综合评分，可稍后再来查看"
          />
        )}
      </Panel>

      {/* ─── 6) AI 分析 ────────────────────────────────────────────── */}
      <div className="detail-tab-panel detail-section">
        {notesLoading || sentimentLoading ? (
          <Panel title="AI分析" padding="md">
            <Skeleton active paragraph={{ rows: 8 }} />
          </Panel>
        ) : (
          <Row gutter={[16, 16]}>
            <Col xs={24} md={12}>
              <Panel
                variant="default"
                className="ai-analysis-panel"
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
                className="ai-analysis-panel"
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
          <Button
            type="primary"
            icon={<RobotOutlined />}
            onClick={() => navigate(`/chat?symbol=${encodeURIComponent(code || '')}`)}
          >
            打开AI助手
          </Button>
        </Panel>
      </div>

      {/* ─── 7) 相关新闻 ───────────────────────────────────────────── */}
      <Panel className="detail-section" title="相关新闻" padding="md">
        <NewsListPanel symbol={code || ''} limit={15} bare />
      </Panel>
    </PageShell>
  );
}