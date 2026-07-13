import { useState, useEffect, type ReactNode } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import './styles.css';
import { Tabs, Spin, Alert, Table, List, Radio, Checkbox, Space, Button } from 'antd';
import { RobotOutlined, ReadOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import {
  useCryptoDetail,
  useCryptoHistory,
  useCryptoIndicators,
  useCryptoSignals,
  useCryptoResearch,
} from '@/hooks/useCrypto';
import KLineChart, { DEFAULT_OVERLAYS } from '@/components/KLineChart';
import Panel from '@/components/Panel';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import StatCard from '@/components/StatCard';
import SectionHeading from '@/components/SectionHeading';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import ThemeTag from '@/components/ThemeTag';
import ReturnTag from '@/components/ReturnTag';
import NewsListPanel from '@/components/NewsListPanel';
import HelpPopover from '@/components/HelpPopover';
import { useSettingsStore } from '@/stores/settings';
import { SENTIMENT_LABELS } from '@/utils/sentiment';
import type { DailyBar, ResearchNote } from '@/types/crypto';
import type { OHLCV } from '@/types/instrument';

/**
 * Apple-style motion layer (scoped to this page):
 * - Response: feedback lands on pointer-down (:active, 0ms), release springs back.
 * - Springs: critically-damped-ish cubic-bezier; transform-only for frame smoothness.
 * - Typography: size-specific tracking (large tight, small loose).
 * - Reduced motion: cross-fade only, transforms disabled.
 */
const ADX_STYLE = `
.adx-crypto-detail {
  /* Critically-damped monotonic curve: y2 ≤ 1, no overshoot. */
  --adx-spring: cubic-bezier(0.32, 0.72, 0, 1);
  --adx-ease-out: cubic-bezier(0.22, 0.9, 0.3, 1);
}
.adx-crypto-detail .ant-btn {
  touch-action: manipulation;
  transition: transform 240ms var(--adx-spring), background-color 140ms var(--adx-ease-out);
}
.adx-crypto-detail .ant-btn:active {
  transform: scale(0.97);
  transition-duration: 0ms;
}
.adx-crypto-detail .ant-radio-button-wrapper,
.adx-crypto-detail .ant-tabs-tab,
.adx-crypto-detail .ant-checkbox-wrapper {
  touch-action: manipulation;
  transition: background-color 140ms var(--adx-ease-out), color 140ms var(--adx-ease-out);
}
.adx-crypto-detail h1,
.adx-crypto-detail h2,
.adx-crypto-detail .ant-typography h1,
.adx-crypto-detail .ant-typography h2 {
  letter-spacing: -0.02em;
  line-height: 1.18;
}
.adx-crypto-detail .ad-text-xs,
.adx-crypto-detail .ad-text-small {
  letter-spacing: 0.01em;
}
@media (prefers-reduced-motion: reduce) {
  .adx-crypto-detail *,
  .adx-crypto-detail *::before,
  .adx-crypto-detail *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }
  .adx-crypto-detail .ant-btn:active {
    transform: none;
  }
}
`;

function AdxShell({ children }: { children: ReactNode }) {
  return (
    <div className="adx-crypto-detail">
      <style>{ADX_STYLE}</style>
      {children}
    </div>
  );
}

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

function toOHLCV(data: DailyBar[]): OHLCV[] {
  return data
    .filter((d) => d.trade_date && d.open != null && d.high != null && d.low != null && d.close != null)
    .map((d) => ({
      trade_date: d.trade_date,
      open: d.open!,
      high: d.high!,
      low: d.low!,
      close: d.close!,
      volume: d.volume ?? 0,
    }));
}

function formatPrice(price?: number | null) {
  if (price == null) return '-';
  if (price < 0.01) return price.toFixed(6);
  if (price < 1) return price.toFixed(4);
  return price.toFixed(2);
}

export default function CryptoDetail() {
  const { code } = useParams<{ code: string }>();
  const navigate = useNavigate();
  const mode = useSettingsStore((s) => s.mode);
  const [timeRange, setTimeRange] = useState(120);
  const { data: crypto, isLoading: detailLoading, error: detailError } = useCryptoDetail(code || '');
  const { data: historyData, isLoading: historyLoading } = useCryptoHistory(code || '', { limit: timeRange });
  const { data: indicator } = useCryptoIndicators(code || '');
  const { data: signals } = useCryptoSignals(code || '', 20);
  const { data: researchNotes } = useCryptoResearch(code || '', 5);

  const [overlays, setOverlays] = useState(() => {
    try {
      const saved = localStorage.getItem('crypto-detail-overlays');
      return saved ? { ...DEFAULT_OVERLAYS, ...JSON.parse(saved) } : DEFAULT_OVERLAYS;
    } catch {
      return DEFAULT_OVERLAYS;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem('crypto-detail-overlays', JSON.stringify(overlays));
    } catch {
      // ignore storage errors
    }
  }, [overlays]);

  if (detailLoading) {
    return (
      <AdxShell>
        <PageShell maxWidth="wide">
          <Spin size="large" className="detail-loading" />
        </PageShell>
      </AdxShell>
    );
  }
  if (detailError) {
    return (
      <AdxShell>
        <PageShell maxWidth="wide">
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/crypto')}
            className="ad-mb-3"
          >
            返回加密货币列表
          </Button>
          <Alert
            className="detail-error"
            message="加载加密货币详情失败"
            description={(detailError as Error).message}
            type="error"
          />
        </PageShell>
      </AdxShell>
    );
  }
  if (!crypto) {
    return (
      <AdxShell>
        <PageShell maxWidth="wide">
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/crypto')}
            className="ad-mb-3"
          >
            返回加密货币列表
          </Button>
          <Alert
            className="detail-error"
            message="币种不存在"
            description={`未找到代码为 ${code} 的加密货币`}
            type="warning"
          />
        </PageShell>
      </AdxShell>
    );
  }

  const ohlcv = toOHLCV(historyData || []);
  const latestNote: ResearchNote | null = researchNotes?.[0] || null;

  const heroStats = [
    { title: '24h最高', termKey: 'high_24h', value: crypto.high_24h, suffix: '$', precision: crypto.high_24h != null && crypto.high_24h < 1 ? 4 : 2 },
    { title: '24h最低', termKey: 'low_24h', value: crypto.low_24h, suffix: '$', precision: crypto.low_24h != null && crypto.low_24h < 1 ? 4 : 2 },
    { title: '24h成交量', termKey: 'volume_24h', value: crypto.volume_24h, suffix: undefined, precision: 2 },
    { title: 'RSI14', termKey: 'rsi14', value: indicator?.rsi14, suffix: undefined, precision: 1 },
  ];

  const formatStatValue = (v?: number | null, precision?: number) => {
    if (v == null) return '—';
    return precision !== undefined ? v.toFixed(precision) : String(v);
  };

  const tabItems = [
    {
      key: 'kline',
      label: 'K线行情',
      children: (
        <Panel title="K线行情" padding="md">
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
          {historyLoading ? (
            <Spin />
          ) : ohlcv.length ? (
            <KLineChart data={ohlcv} overlays={overlays} />
          ) : (
            <Alert className="detail-chart__empty" message="暂无历史行情数据" type="info" showIcon />
          )}
        </Panel>
      ),
    },
    {
      key: 'signals',
      label: '交易信号',
      children: (
        <Panel title="最近信号" padding="md">
          <Table
            dataSource={signals || []}
            rowKey="id"
            size="small"
            pagination={{ pageSize: 10 }}
            scroll={{ x: 'max-content' }}
            columns={[
              { title: '日期', dataIndex: 'trade_date' },
              { title: <HelpPopover termKey="signal_type" mode={mode}>信号</HelpPopover>, dataIndex: 'signal_type' },
              { title: <HelpPopover termKey="strength" mode={mode}>强度</HelpPopover>, dataIndex: 'strength', render: (v: any) => <span className="tabular-nums">{v}</span> },
            ]}
          />
        </Panel>
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
      key: 'ai',
      label: (
        <span>
          <RobotOutlined className="detail-tab-icon" />
          AI研究
        </span>
      ),
      children: (
        <Panel
          variant="default"
          title={
            <span>
              <ReadOutlined className="detail-tab-icon detail-tab-icon--lg" />
              AI 研究笔记
            </span>
          }
          padding="md"
        >
          {latestNote ? (
            <div>
              <div className="ai-note-meta">
                {latestNote.note_type && (
                  <span className="ai-note-type">
                    <HelpPopover termKey="note_type" mode={mode}>{latestNote.note_type}</HelpPopover>
                  </span>
                )}
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
                    <HelpPopover termKey="sentiment_confidence" mode={mode}>置信度</HelpPopover> {latestNote.confidence}/10
                  </span>
                )}
                <span className="ai-note-time">{latestNote.generated_at?.slice(0, 16)}</span>
              </div>
              <p className="ai-note-summary">{latestNote.summary}</p>
              <p className="ai-note-content">{latestNote.content}</p>
            </div>
          ) : (
            <div className="ai-empty">
              <RobotOutlined className="ai-empty__icon" />
              <p>暂无AI研报</p>
            </div>
          )}

          {researchNotes && researchNotes.length > 1 && (
            <List
              className="detail-list ad-list-compact"
              dataSource={researchNotes.slice(1)}
              renderItem={(note: ResearchNote) => (
                <List.Item>
                  <List.Item.Meta
                    title={
                      <div className="ai-note-meta">
                        <span className="ai-note-type">{note.note_type}</span>
                        {note.sentiment && (
                          <ThemeTag
                            variant={
                              note.sentiment === 'bullish' || note.sentiment === 'positive'
                                ? 'rise'
                                : note.sentiment === 'bearish' || note.sentiment === 'negative'
                                  ? 'fall'
                                  : 'neutral'
                            }
                          >
                            {SENTIMENT_LABELS[note.sentiment] || note.sentiment}
                          </ThemeTag>
                        )}
                        <span className="ai-note-time">{note.generated_at?.slice(0, 16)}</span>
                      </div>
                    }
                    description={
                      <p className="ai-note-content">{note.summary}</p>
                    }
                  />
                </List.Item>
              )}
            />
          )}
        </Panel>
      ),
    },
  ];

  return (
    <AdxShell>
      <PageShell maxWidth="wide">
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/crypto')}
          className="ad-mb-3"
        >
          返回加密货币列表
        </Button>
      <PageHeader
        eyebrow="加密货币"
        title={crypto.name}
        description={[
          crypto.exchange && `交易所: ${crypto.exchange}`,
          crypto.currency && `计价: ${crypto.currency}`,
          crypto.category,
        ].filter(Boolean).join(' · ')}
        extra={
          <div className="detail-hero__kpi">
            <div className="detail-hero__kpi-value tabular-nums">
              {crypto.price != null ? `$${formatPrice(crypto.price)}` : '-'}
            </div>
            <div className="detail-hero__kpi-tag">
              <ReturnTag value={crypto.change_pct ?? crypto.change_24h} />
            </div>
          </div>
        }
      />

      <div className="detail-hero">
        <InstrumentCodeTag code={crypto.code} name={crypto.name} />
        {crypto.category && <ThemeTag>{crypto.category}</ThemeTag>}
        {crypto.market && <ThemeTag variant="accent">{crypto.market}</ThemeTag>}
      </div>

      <SectionHeading title="核心指标" />
      <ResponsiveGrid cols={4} gap="md" className="detail-section">
        {heroStats.map((stat) => (
          <StatCard
            key={stat.title}
            title={
              stat.termKey ? (
                <HelpPopover termKey={stat.termKey} mode={mode}>{stat.title}</HelpPopover>
              ) : stat.title
            }
            value={formatStatValue(stat.value, stat.precision)}
            suffix={stat.suffix}
          />
        ))}
      </ResponsiveGrid>

        <Tabs items={tabItems} defaultActiveKey="kline" />
      </PageShell>
    </AdxShell>
  );
}
