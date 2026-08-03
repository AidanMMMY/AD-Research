import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Input, Button, Slider, Tooltip, Tag, message } from 'antd';
import { SmileOutlined, FrownOutlined, MehOutlined, SyncOutlined } from '@ant-design/icons';
import { researchApi, SentimentAggregate } from '@/api/research';
import AISetupBanner from "@/components/AISetupBanner";
import FilterToolbar from '@/components/FilterToolbar';
import EmptyState from '@/components/EmptyState';
import ErrorState from '@/components/ErrorState';
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
/* Accessibility: prefers-reduced-transparency. Panel surfaces on this
   page should fall back to solid backgrounds when the user opts out of
   translucent materials — covers any future backdrop-filter layer as
   well as the current translucent variants. */
@media (prefers-reduced-transparency: reduce) {
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

/**
 * 单标情绪分析面板（审计 P1-5，2026-08-02）：
 * 原 /instrument-sentiment 独立页并入 /sentiment 页内「单标情绪」Tab，
 * 本组件作为内嵌面板使用（PageShell/PageHeader 由宿主页提供）。
 * initialCode 用于从标的详情页等入口带 code 跳入时预填并自动分析一次。
 */
export default function InstrumentSentimentPanel({ initialCode }: { initialCode?: string }) {
  const [code, setCode] = useState(initialCode ?? '');
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [days, setDays] = useState(7);
  // Slider draft value: the thumb tracks the pointer 1:1 via local state and
  // only commits to the query-driving `days` on release (velocity-free snap).
  const [daysDraft, setDaysDraft] = useState(7);

  // 分析成功后把当前标的回写 ?code=（replace，不污染历史栈），让地址栏可分享。
  // 与宿主 /sentiment 页共用同一个 useSearchParams 实例（react-router v6 同一份），
  // 保留 tab=instrument 及其余既有参数。
  const [searchParams, setSearchParams] = useSearchParams();
  const syncCodeToUrl = (c: string) => {
    if (searchParams.get('code') === c) return; // 已同步（含带 code 跳入的自动分析）
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set('tab', 'instrument');
        next.set('code', c);
        return next;
      },
      { replace: true },
    );
  };

  // 审计 P1（2026-08-03）：查询与 mutation 都要显式承接错误 ——
  // 失败时 message.error 提示 + 错误态重试出口，不能静默落入空态。
  const { data: sentiment, isLoading, isError, refetch } = useQuery({
    queryKey: ['sentiment', selectedCode, days],
    queryFn: () =>
      selectedCode
        ? researchApi.getSentiment(selectedCode, days).then((r) => r.data)
        : Promise.resolve(null),
    enabled: !!selectedCode,
  });

  const ingestMutation = useMutation({
    mutationFn: (code: string) => researchApi.ingestSentiment(code, days),
    onSuccess: (_res, ingestedCode) => {
      syncCodeToUrl(ingestedCode);
      refetch();
    },
    onError: (err: any) => {
      message.error(err?.response?.data?.detail ?? '情绪分析失败，请稍后重试');
    },
  });

  const handleLookup = (target?: string) => {
    const c = (target ?? code).trim().toUpperCase();
    if (!c) return;
    setCode(c);
    setSelectedCode(c);
    ingestMutation.mutate(c);
  };

  // 带 code 参数跳入时（如详情页空态「前往分析」）自动跑一次分析，仅首次
  const autoRanRef = useRef(false);
  useEffect(() => {
    if (!autoRanRef.current && initialCode) {
      autoRanRef.current = true;
      handleLookup(initialCode);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialCode]);

  return (
    <AdxShell>
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
        ) : isError ? (
          <ErrorState
            className="ad-mt-9"
            description={`${selectedCode} 的情绪数据加载失败，请稍后重试`}
            onRetry={() => refetch()}
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
    <Panel variant="minimal">
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
