import { useState, type ReactNode } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Input, Button, Slider, Tooltip, Tag } from 'antd';
import { SmileOutlined, FrownOutlined, MehOutlined, SyncOutlined } from '@ant-design/icons';
import { researchApi, SentimentAggregate } from '@/api/research';
import AISetupBanner from "@/components/AISetupBanner";
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import EmptyState from '@/components/EmptyState';
import LoadingBlock from '@/components/LoadingBlock';
import Panel from '@/components/Panel';
import ThemeTag from '@/components/ThemeTag';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import HelpPopover from '@/components/HelpPopover';
import { useSettingsStore } from '@/stores/settings';

/**
 * Apple-style motion layer (scoped to this page):
 * - Response: feedback lands on pointer-down (:active, 0ms), release springs back.
 * - Springs: critically-damped-ish cubic-bezier; transform-only for frame smoothness.
 * - Direct manipulation: the slider thumb tracks the pointer 1:1 (local draft
 *   state) and only commits the query on release (see onChangeComplete below).
 * - Typography: size-specific tracking (large tight, small loose).
 * - Reduced motion: cross-fade only, transforms disabled.
 */
const ADX_STYLE = `
.adx-sentiment-dashboard {
  /* Critically-damped monotonic curve: y2 ≤ 1, no overshoot. */
  --adx-spring: cubic-bezier(0.32, 0.72, 0, 1);
  --adx-ease-out: cubic-bezier(0.22, 0.9, 0.3, 1);
}
.adx-sentiment-dashboard .ant-btn {
  touch-action: manipulation;
  transition: transform 240ms var(--adx-spring), background-color 140ms var(--adx-ease-out);
}
.adx-sentiment-dashboard .ant-btn:active {
  transform: scale(0.97);
  transition-duration: 0ms;
}
.adx-sentiment-dashboard .ant-slider-handle {
  transition: box-shadow 140ms var(--adx-ease-out);
}
.adx-sentiment-dashboard .ant-slider-handle:active {
  box-shadow: 0 0 0 6px var(--bg-active);
}
/* Use transform: scaleX() instead of animating width — width triggers
   layout, scaleX is a pure composite op and stays at 60fps.
   The fill needs an explicit 100% width so scaleX has a reference frame. */
.adx-sentiment-dashboard .ad-sentiment-bar__fill {
  width: 100%;
  transform-origin: left center;
  transition: transform 480ms var(--adx-spring);
}
/* Hot-instrument quick-entry chips on the empty state. */
.adx-sentiment-dashboard .sentiment-hot-chip {
  cursor: pointer;
  user-select: none;
}
.adx-sentiment-dashboard h1,
.adx-sentiment-dashboard h2,
.adx-sentiment-dashboard .ant-typography h1,
.adx-sentiment-dashboard .ant-typography h2 {
  letter-spacing: -0.02em;
  line-height: 1.18;
}
.adx-sentiment-dashboard .ad-text-xs,
.adx-sentiment-dashboard .ad-text-small {
  letter-spacing: 0.01em;
}
@media (prefers-reduced-motion: reduce) {
  .adx-sentiment-dashboard *,
  .adx-sentiment-dashboard *::before,
  .adx-sentiment-dashboard *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }
  .adx-sentiment-dashboard .ant-btn:active {
    transform: none;
  }
}
/* Accessibility: prefers-reduced-transparency. Panel surfaces (including
   the glass-card variant) on this page should fall back to solid
   backgrounds when the user opts out of translucent materials — covers
   any future backdrop-filter layer as well as the current translucent
   variants. */
@media (prefers-reduced-transparency: reduce) {
  .adx-sentiment-dashboard .glass-card,
  .adx-sentiment-dashboard .ad-panel {
    background: var(--card-bg) !important;
    backdrop-filter: none !important;
    -webkit-backdrop-filter: none !important;
  }
}
`;

function AdxShell({ children }: { children: ReactNode }) {
  return (
    <div className="adx-sentiment-dashboard">
      <style>{ADX_STYLE}</style>
      {children}
    </div>
  );
}

const SENTIMENT_ICONS: Record<string, React.ReactNode> = {
  positive: <SmileOutlined className="sentiment-icon--positive" />,
  negative: <FrownOutlined className="sentiment-icon--negative" />,
  neutral: <MehOutlined className="sentiment-icon--neutral" />,
};

/** Popular instruments offered as one-click entry points on the empty state. */
const HOT_CODES = ['510300.SH', '159915.SZ', 'SPY.US', 'BTC.US'];

export default function SentimentDashboard() {
  const [code, setCode] = useState('');
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [days, setDays] = useState(7);
  // Slider draft value: the thumb tracks the pointer 1:1 via local state and
  // only commits to the query-driving `days` on release (velocity-free snap).
  const [daysDraft, setDaysDraft] = useState(7);

  const { data: sentiment, isLoading, refetch } = useQuery({
    queryKey: ['sentiment', selectedCode, days],
    queryFn: () =>
      selectedCode
        ? researchApi.getSentiment(selectedCode, days).then((r) => r.data)
        : Promise.resolve(null),
    enabled: !!selectedCode,
  });

  const ingestMutation = useMutation({
    mutationFn: (code: string) => researchApi.ingestSentiment(code, days),
    onSuccess: () => refetch(),
  });

  const handleLookup = (target?: string) => {
    const c = (target ?? code).trim().toUpperCase();
    if (!c) return;
    setCode(c);
    setSelectedCode(c);
    ingestMutation.mutate(c);
  };

  return (
    <AdxShell>
      <PageShell maxWidth="wide">
        <PageHeader
          eyebrow="市场情绪"
          title="单标情绪分析"
          description="基于新闻情绪分析，评估市场对特定标的的情绪倾向"
        />
      <AISetupBanner />
      <FilterToolbar>
        <Input
          placeholder="标的代码 (如 AAPL.US)"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onPressEnter={() => handleLookup()}
          className="ad-form-row__grow"
        />
        <span className="ad-text-small ad-text-tertiary ad-whitespace-nowrap">
          回溯 {daysDraft} 天
        </span>
        <div style={{ flex: 1, minWidth: 120 }}>
          <Slider
            min={1}
            max={30}
            value={daysDraft}
            onChange={setDaysDraft}
            onChangeComplete={(v) => {
              setDaysDraft(v);
              setDays(v);
            }}
            tooltip={{ formatter: (v) => `${v}天` }}
          />
        </div>
        <Button
          type="primary"
          icon={<SyncOutlined spin={ingestMutation.isPending} />}
          loading={ingestMutation.isPending}
          onClick={() => handleLookup()}
        >
          分析情绪
        </Button>
      </FilterToolbar>

      <div className="ad-mt-5">
        {isLoading ? (
          <LoadingBlock size="lg" />
        ) : !selectedCode ? (
          <EmptyState
            className="ad-mt-9"
            title="开始情绪分析"
            description="输入标的代码，选择回溯天数，点击分析按钮；或直接挑一个热门标的"
            action={
              <>
                {HOT_CODES.map((c) => (
                  <Tag
                    key={c}
                    className="sentiment-hot-chip"
                    onClick={() => handleLookup(c)}
                  >
                    {c}
                  </Tag>
                ))}
              </>
            }
          />
        ) : !sentiment ? (
          <EmptyState
            className="ad-mt-9"
            title="暂无情绪数据"
            description={`暂无 ${selectedCode} 的情绪数据。请等待新闻抓取完成后重试。`}
          />
        ) : (
          <SentimentCard sentiment={sentiment} />
        )}
      </div>
      </PageShell>
    </AdxShell>
  );
}

function SentimentCard({ sentiment }: { sentiment: SentimentAggregate }) {
  const mode = useSettingsStore((s) => s.mode);
  const scorePct = ((sentiment.avg_score + 1) / 2) * 100; // map -1..1 to 0..100

  const tagVariant =
    sentiment.label === 'positive' ? 'rise' :
    sentiment.label === 'negative' ? 'fall' : 'neutral';

  return (
    <Panel variant="minimal" className="glass-card">
      <div className="ad-text-center">
        <div className="ad-text-small ad-text-tertiary ad-mb-1">
          <InstrumentCodeTag
            code={sentiment.instrument_code}
            name={sentiment.name}
            name_zh={sentiment.name_zh}
          />
        </div>
        <div className="sentiment-icon-wrapper">
          {SENTIMENT_ICONS[sentiment.label] || SENTIMENT_ICONS.neutral}
        </div>
        <div
          className={`sentiment-score-value ${sentiment.label ? `sentiment-score-value--${sentiment.label}` : 'sentiment-score-value--neutral'}`}
        >
          <HelpPopover termKey="sentiment_score" mode={mode}>
            {sentiment.avg_score.toFixed(2)}
          </HelpPopover>
        </div>
        <div className="ad-mt-2">
          <ThemeTag variant={tagVariant}>
            {sentiment.label === 'positive' ? '看多' :
             sentiment.label === 'negative' ? '看空' : '中性'}
          </ThemeTag>
        </div>

        {/* Score bar — flat accent fill (composited, not layout) */}
        <div className="ad-sentiment-bar">
          <div
            className="ad-sentiment-bar__fill"
            style={{ transform: `scaleX(${scorePct / 100})` }}
          />
          <div className="ad-sentiment-bar__center" />
        </div>

        <div className="ad-flex ad-justify-center ad-gap-5">
          <Tooltip title="正面">
            <span className="sentiment-count sentiment-count--positive">
              <SmileOutlined /> {sentiment.positive_count}
            </span>
          </Tooltip>
          <Tooltip title="中性">
            <span className="sentiment-count sentiment-count--neutral">
              <MehOutlined /> {sentiment.neutral_count}
            </span>
          </Tooltip>
          <Tooltip title="负面">
            <span className="sentiment-count sentiment-count--negative">
              <FrownOutlined /> {sentiment.negative_count}
            </span>
          </Tooltip>
        </div>
        <div className="ad-text-small ad-text-tertiary ad-mt-2">
          共 {sentiment.total_articles} 篇文章 · 近 {sentiment.period_days} 天
        </div>
      </div>
    </Panel>
  );
}
