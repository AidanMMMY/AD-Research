import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Input, Button, Slider, Tag, Tooltip, Skeleton, Empty } from 'antd';
import { SmileOutlined, FrownOutlined, MehOutlined, SyncOutlined } from '@ant-design/icons';
import { researchApi, SentimentAggregate } from '@/api/research';
import AISetupBanner from "@/components/AISetupBanner";
import GlassCard from '@/components/GlassCard';

const SENTIMENT_ICONS: Record<string, React.ReactNode> = {
  positive: <SmileOutlined style={{ color: '#22c55e', fontSize: 24 }} />,
  negative: <FrownOutlined style={{ color: '#ef4444', fontSize: 24 }} />,
  neutral: <MehOutlined style={{ color: '#eab308', fontSize: 24 }} />,
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
      <AISetupBanner />
      <GlassCard>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <Input
            placeholder="标的代码 (如 AAPL.US)"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onPressEnter={handleLookup}
            style={{ flex: 1, minWidth: 200 }}
          />
          <span style={{ fontSize: 12, color: '#64748b', whiteSpace: 'nowrap' }}>
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

      <div style={{ marginTop: 20 }}>
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
    sentiment.label === 'positive' ? '#22c55e' :
    sentiment.label === 'negative' ? '#ef4444' : '#eab308';

  return (
    <GlassCard>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 14, color: '#94a3b8', marginBottom: 4 }}>
          {sentiment.instrument_code}
        </div>
        <div style={{ fontSize: 48, marginTop: 4 }}>
          {SENTIMENT_ICONS[sentiment.label] || SENTIMENT_ICONS.neutral}
        </div>
        <div
          style={{
            fontSize: 36,
            fontWeight: 700,
            color,
            fontFamily: "'SF Mono', monospace",
            marginTop: 4,
          }}
        >
          {sentiment.avg_score.toFixed(2)}
        </div>
        <Tag
          color={
            sentiment.label === 'positive' ? 'green' :
            sentiment.label === 'negative' ? 'red' : 'gold'
          }
          style={{ fontSize: 14, padding: '4px 16px', marginTop: 8 }}
        >
          {sentiment.label === 'positive' ? '看多' :
           sentiment.label === 'negative' ? '看空' : '中性'}
        </Tag>

        {/* Score bar */}
        <div
          style={{
            margin: '20px auto 0',
            maxWidth: 320,
            height: 8,
            borderRadius: 4,
            background: 'rgba(255,255,255,0.06)',
            position: 'relative',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: `${scorePct}%`,
              height: '100%',
              borderRadius: 4,
              background: `linear-gradient(90deg, #ef4444, #eab308, #22c55e)`,
              backgroundSize: '320px 100%',
              backgroundPosition: `${(1 - scorePct / 100) * 320}px 0`,
            }}
          />
          <div
            style={{
              position: 'absolute',
              top: -4,
              left: '50%',
              width: 2,
              height: 16,
              background: '#fff',
              borderRadius: 1,
              opacity: 0.3,
            }}
          />
        </div>

        <div style={{ display: 'flex', justifyContent: 'center', gap: 32, marginTop: 20 }}>
          <Tooltip title="正面">
            <span style={{ color: '#22c55e', fontSize: 14, fontWeight: 600 }}>
              <SmileOutlined /> {sentiment.positive_count}
            </span>
          </Tooltip>
          <Tooltip title="中性">
            <span style={{ color: '#eab308', fontSize: 14, fontWeight: 600 }}>
              <MehOutlined /> {sentiment.neutral_count}
            </span>
          </Tooltip>
          <Tooltip title="负面">
            <span style={{ color: '#ef4444', fontSize: 14, fontWeight: 600 }}>
              <FrownOutlined /> {sentiment.negative_count}
            </span>
          </Tooltip>
        </div>
        <div style={{ fontSize: 12, color: '#475569', marginTop: 12 }}>
          共 {sentiment.total_articles} 篇文章 · 近 {sentiment.period_days} 天
        </div>
      </div>
    </GlassCard>
  );
}
