import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Tabs } from 'antd';
import { useScores, useScoreTemplates } from '@/hooks/useScores';
import GlassCard from '@/components/GlassCard';
import ETFCodeTag from '@/components/ETFCodeTag';
import ScoreBar from '@/components/ScoreBar';

export default function ScoreRanking() {
  const navigate = useNavigate();
  const [templateId, setTemplateId] = useState<number | undefined>();
  const { data: scoresData } = useScores({ template_id: templateId, limit: 50 });
  const { data: templates } = useScoreTemplates();

  const columns = [
    {
      title: '全市场排名',
      dataIndex: 'rank_overall',
      width: 90,
      render: (v: number) => (
        <span style={{ fontWeight: 700, color: v <= 3 ? '#eab308' : '#94a3b8', fontFamily: "'SF Mono', monospace" }}>
          {v <= 3 && '🏆 '}{v}
        </span>
      ),
    },
    {
      title: '分类排名',
      dataIndex: 'rank_category',
      width: 90,
      render: (v: number) => (
        <span style={{ fontFamily: "'SF Mono', monospace", color: '#64748b' }}>{v}</span>
      ),
    },
    {
      title: 'ETF',
      render: (_: unknown, record: any) => <ETFCodeTag code={record.etf_code} name={record.etf_name} />,
    },
    {
      title: '综合评分',
      render: (_: unknown, record: any) => <ScoreBar score={record.composite_score} />,
      width: 180,
    },
    {
      title: '收益',
      dataIndex: 'score_return',
      width: 80,
      render: (v: number) => <span style={{ fontFamily: "'SF Mono', monospace", color: '#94a3b8' }}>{v?.toFixed(1)}</span>,
    },
    {
      title: '风险',
      dataIndex: 'score_risk',
      width: 80,
      render: (v: number) => <span style={{ fontFamily: "'SF Mono', monospace", color: '#94a3b8' }}>{v?.toFixed(1)}</span>,
    },
    {
      title: '夏普',
      dataIndex: 'score_sharpe',
      width: 80,
      render: (v: number) => <span style={{ fontFamily: "'SF Mono', monospace", color: '#94a3b8' }}>{v?.toFixed(1)}</span>,
    },
    {
      title: '流动性',
      dataIndex: 'score_liquidity',
      width: 90,
      render: (v: number) => <span style={{ fontFamily: "'SF Mono', monospace", color: '#94a3b8' }}>{v?.toFixed(1)}</span>,
    },
    {
      title: '趋势',
      dataIndex: 'score_trend',
      width: 80,
      render: (v: number) => <span style={{ fontFamily: "'SF Mono', monospace", color: '#94a3b8' }}>{v?.toFixed(1)}</span>,
    },
  ];

  const tabItems = templates?.map((t) => ({
    key: String(t.id),
    label: t.name,
  })) || [];

  return (
    <div>
      <GlassCard style={{ marginBottom: 20 }}>
        <Tabs
          activeKey={String(templateId || templates?.find((t) => t.is_default)?.id || '')}
          onChange={(key) => setTemplateId(Number(key))}
          items={tabItems}
          style={{ marginBottom: 0 }}
        />
      </GlassCard>

      <GlassCard title={`综合评分 Top ${scoresData?.items.length || 0}`}>
        <Table
          dataSource={scoresData?.items || []}
          columns={columns}
          rowKey="etf_code"
          size="small"
          pagination={false}
          onRow={(record) => ({
            onClick: () => navigate(`/etfs/${record.etf_code}`),
          })}
        />
      </GlassCard>
    </div>
  );
}
