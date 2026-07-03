import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Input, Button, Slider, Tooltip, Skeleton, Empty } from 'antd';
import { SmileOutlined, FrownOutlined, MehOutlined, SyncOutlined } from '@ant-design/icons';
import { researchApi, SentimentAggregate } from '@/api/research';
import AISetupBanner from "@/components/AISetupBanner";
import GlassCard from '@/components/GlassCard';
import ThemeTag from '@/components/ThemeTag';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import HelpPopover from '@/components/HelpPopover';

const SENTIMENT_ICONS: Record<string, React.ReactNode> = {
  positive: <SmileOutlined className="sentiment-icon--positive" />,
  negative: <FrownOutlined className="sentiment-icon--negative" />,
  neutral: <MehOutlined className="sentiment-icon--neutral" />,
};

export default function SentimentDashboard() {
  const [code, setCode] = useState('');
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [days, setDays] = useState(7);

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

  const handleLookup = () => {
    if (!code.trim()) return;
    const c = code.trim().toUpperCase();
    setSelectedCode(c);
    ingestMutation.mutate(c);
  };

  return (
    <div>
      <h1 className="page-header-title">情绪看板</h1>
      <p className="page-header-description ad-mb-8">基于新闻情绪分析，评估市场对特定标的的情绪倾向</p>
      <AISetupBanner />
      <GlassCard>
        <div className="phase5c-flex-wrap">
          <Input
            placeholder="标的代码 (如 AAPL.US)"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onPressEnter={handleLookup}
            className="ad-form-row__grow"
          />
          <span className="ad-text-small ad-text-tertiary ad-whitespace-nowrap">
            回溯 {days} 天
          </span>
          <Slider
            min={1}
            max={30}
            value={days}
            onChange={setDays}
            className="ad-slider--sm"
            tooltip={{ formatter: (v) => `${v}天` }}
          />
          <Button
            type="primary"
            icon={<SyncOutlined spin={ingestMutation.isPending} />}
            loading={ingestMutation.isPending}
            onClick={handleLookup}
          >
            分析情绪
          </Button>
        </div>
      </GlassCard>

      <div className="ad-mt-5">
        {isLoading ? (
          <Skeleton active paragraph={{ rows: 8 }} />
        ) : !selectedCode ? (
          <Empty description="输入标的代码开始情绪分析" className="ad-mt-9" />
        ) : !sentiment ? (
          <Empty description={`暂无 ${selectedCode} 的情绪数据。请等待新闻抓取完成后重试`} className="ad-mt-9" />
        ) : (
          <SentimentCard sentiment={sentiment} />
        )}
      </div>
    </div>
  );
}

function SentimentCard({ sentiment }: { sentiment: SentimentAggregate }) {
  const scorePct = ((sentiment.avg_score + 1) / 2) * 100; // map -1..1 to 0..100

  const tagVariant =
    sentiment.label === 'positive' ? 'rise' :
    sentiment.label === 'negative' ? 'fall' : 'neutral';

  return (
    <GlassCard>
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
          <HelpPopover termKey="sentiment_score">
            {sentiment.avg_score.toFixed(2)}
          </HelpPopover>
        </div>
        <div className="ad-mt-2">
          <ThemeTag variant={tagVariant}>
            {sentiment.label === 'positive' ? '看多' :
             sentiment.label === 'negative' ? '看空' : '中性'}
          </ThemeTag>
        </div>

        {/* Score bar — flat accent fill */}
        <div className="ad-sentiment-bar">
          <div
            className="ad-sentiment-bar__fill"
            style={{ width: `${scorePct}%` }}
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
    </GlassCard>
  );
}
