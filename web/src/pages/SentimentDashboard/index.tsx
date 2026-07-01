import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Input, Button, Slider, Tooltip, Skeleton, Empty } from 'antd';
import { SmileOutlined, FrownOutlined, MehOutlined, SyncOutlined } from '@ant-design/icons';
import { researchApi, SentimentAggregate } from '@/api/research';
import AISetupBanner from "@/components/AISetupBanner";
import GlassCard from '@/components/GlassCard';
import ThemeTag from '@/components/ThemeTag';

const SENTIMENT_ICONS: Record<string, React.ReactNode> = {
  positive: <SmileOutlined style={{ color: 'var(--color-rise)', fontSize: 24 }} />,
  negative: <FrownOutlined style={{ color: 'var(--color-fall)', fontSize: 24 }} />,
  neutral: <MehOutlined style={{ color: 'var(--text-tertiary)', fontSize: 24 }} />,
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
      <h1 style={{ fontSize: 'var(--text-h1-size)', fontWeight: 500, color: 'var(--text-primary)', margin: '0 0 8px', letterSpacing: '-0.03em' }}>情绪看板</h1>
      <p style={{ margin: '0 0 32px', color: 'var(--text-tertiary)', fontSize: 'var(--text-body-size)' }}>基于新闻情绪分析，评估市场对特定标的的情绪倾向</p>
      <AISetupBanner />
      <GlassCard>
        <div style={{ display: 'flex', gap: 'var(--space-sm)', flexWrap: 'wrap', alignItems: 'center' }}>
          <Input
            placeholder="标的代码 (如 AAPL.US)"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onPressEnter={handleLookup}
            style={{ flex: 1, minWidth: 200 }}
          />
          <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }}>
            回溯 {days} 天
          </span>
          <Slider
            min={1}
            max={30}
            value={days}
            onChange={setDays}
            style={{ width: 120 }}
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

      <div style={{ marginTop: 'var(--space-lg)' }}>
        {isLoading ? (
          <Skeleton active paragraph={{ rows: 8 }} />
        ) : !selectedCode ? (
          <Empty description="输入标的代码开始情绪分析" style={{ marginTop: 60 }} />
        ) : !sentiment ? (
          <Empty description={`暂无 ${selectedCode} 的情绪数据。请等待新闻抓取完成后重试`} style={{ marginTop: 60 }} />
        ) : (
          <SentimentCard sentiment={sentiment} />
        )}
      </div>
    </div>
  );
}

function SentimentCard({ sentiment }: { sentiment: SentimentAggregate }) {
  const scorePct = ((sentiment.avg_score + 1) / 2) * 100; // map -1..1 to 0..100
  const color =
    sentiment.label === 'positive' ? 'var(--color-rise)' :
    sentiment.label === 'negative' ? 'var(--color-fall)' : 'var(--text-tertiary)';

  const tagVariant =
    sentiment.label === 'positive' ? 'rise' :
    sentiment.label === 'negative' ? 'fall' : 'neutral';

  return (
    <GlassCard>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)', marginBottom: 'var(--space-xs)' }}>
          {sentiment.instrument_code}
        </div>
        <div style={{ fontSize: 'var(--text-data-xl-size)', marginTop: 'var(--space-xs)' }}>
          {SENTIMENT_ICONS[sentiment.label] || SENTIMENT_ICONS.neutral}
        </div>
        <div
          style={{
            fontSize: 40,
            fontWeight: 700,
            color,
            fontFamily: "'SF Mono', monospace",
            marginTop: 'var(--space-xs)',
          }}
        >
          {sentiment.avg_score.toFixed(2)}
        </div>
        <div style={{ marginTop: 'var(--space-sm)' }}>
          <ThemeTag variant={tagVariant}>
            {sentiment.label === 'positive' ? '看多' :
             sentiment.label === 'negative' ? '看空' : '中性'}
          </ThemeTag>
        </div>

        {/* Score bar — flat accent fill */}
        <div
          style={{
            margin: 'var(--space-lg) auto 0',
            maxWidth: 320,
            height: 8,
            borderRadius: 'var(--radius-sm)',
            background: 'var(--bg-hover)',
            position: 'relative',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: `${scorePct}%`,
              height: '100%',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--accent)',
            }}
          />
          <div
            style={{
              position: 'absolute',
              top: -4,
              left: '50%',
              width: 2,
              height: 16,
              background: 'var(--text-primary)',
              borderRadius: 1,
              opacity: 0.3,
            }}
          />
        </div>

        <div style={{ display: 'flex', justifyContent: 'center', gap: 'var(--space-lg)', marginTop: 'var(--space-lg)' }}>
          <Tooltip title="正面">
            <span style={{ color: 'var(--color-rise)', fontSize: 14, fontWeight: 600 }}>
              <SmileOutlined /> {sentiment.positive_count}
            </span>
          </Tooltip>
          <Tooltip title="中性">
            <span style={{ color: 'var(--text-tertiary)', fontSize: 14, fontWeight: 600 }}>
              <MehOutlined /> {sentiment.neutral_count}
            </span>
          </Tooltip>
          <Tooltip title="负面">
            <span style={{ color: 'var(--color-fall)', fontSize: 14, fontWeight: 600 }}>
              <FrownOutlined /> {sentiment.negative_count}
            </span>
          </Tooltip>
        </div>
        <div style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)', marginTop: 'var(--space-sm)' }}>
          共 {sentiment.total_articles} 篇文章 · 近 {sentiment.period_days} 天
        </div>
      </div>
    </GlassCard>
  );
}
