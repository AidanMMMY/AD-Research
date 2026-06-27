import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Tabs } from 'antd';
import { useScores, useScoreTemplates } from '@/hooks/useScores';
import { useAIHelp } from '@/hooks/useAIHelp';
import Panel from '@/components/Panel';
import HelpTrigger from '@/components/HelpTrigger';
import HelpPopover from '@/components/HelpPopover';
import ETFCodeTag from '@/components/ETFCodeTag';
import ScoreBar from '@/components/ScoreBar';
import { buildScoreRankingContext } from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';

export default function ScoreRanking() {
  const navigate = useNavigate();
  const { open } = useAIHelp();
  const [templateId, setTemplateId] = useState<number | undefined>();
  const { data: scoresData } = useScores({ template_id: templateId, limit: 50 });
  const { data: templates } = useScoreTemplates();

  const activeTemplate = templates?.find((t) =>
    templateId ? t.id === templateId : t.is_default
  );

  const handleOpenHelp = () => {
    open({
      pageType: 'score_ranking',
      pageTitle: '评分排名',
      contextData: buildScoreRankingContext(scoresData, activeTemplate?.name, activeTemplate?.id),
      quickQuestions: getQuickQuestions('score_ranking'),
    });
  };

  const columns = [
    {
      title: <HelpPopover termKey="rank_overall">全市场排名</HelpPopover>,
      dataIndex: 'rank_overall',
      width: 90,
      render: (v: number) => (
        <span style={{ fontWeight: 700, color: v <= 3 ? 'var(--accent)' : 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
          {v <= 3 && '🏆 '}{v}
        </span>
      ),
    },
    {
      title: <HelpPopover termKey="rank_category">分类排名</HelpPopover>,
      dataIndex: 'rank_category',
      width: 90,
      render: (v: number) => (
        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)' }}>{v}</span>
      ),
    },
    {
      title: '标的',
      render: (_: unknown, record: any) => <ETFCodeTag code={record.etf_code} name={record.etf_name} />,
    },
    {
      title: <HelpPopover termKey="composite_score">综合评分</HelpPopover>,
      render: (_: unknown, record: any) => <ScoreBar score={record.composite_score} />,
      width: 180,
    },
    { title: <HelpPopover termKey="score_return">收益</HelpPopover>, dataIndex: 'score_return', width: 80, render: (v: number) => <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{v?.toFixed(1)}</span> },
    { title: <HelpPopover termKey="score_risk">风险</HelpPopover>, dataIndex: 'score_risk', width: 80, render: (v: number) => <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{v?.toFixed(1)}</span> },
    { title: <HelpPopover termKey="score_sharpe">夏普</HelpPopover>, dataIndex: 'score_sharpe', width: 80, render: (v: number) => <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{v?.toFixed(1)}</span> },
    { title: <HelpPopover termKey="score_liquidity">流动性</HelpPopover>, dataIndex: 'score_liquidity', width: 90, render: (v: number) => <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{v?.toFixed(1)}</span> },
    { title: <HelpPopover termKey="score_trend">趋势</HelpPopover>, dataIndex: 'score_trend', width: 80, render: (v: number) => <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{v?.toFixed(1)}</span> },
  ];

  const tabItems = templates?.map((t) => ({
    key: String(t.id),
    label: t.name,
  })) || [];

  return (
    <div>
      <Panel style={{ marginBottom: 20 }}>
        <Tabs
          activeKey={String(templateId || templates?.find((t) => t.is_default)?.id || '')}
          onChange={(key) => setTemplateId(Number(key))}
          items={tabItems}
          style={{ marginBottom: 0 }}
        />
      </Panel>

      <Panel
        title={`综合评分 Top ${scoresData?.items.length || 0}`}
        extra={
          <HelpTrigger
            tooltip="AI 解释评分逻辑"
            onClick={handleOpenHelp}
          />
        }
      >
        <Table
          dataSource={scoresData?.items || []}
          columns={columns}
          rowKey="etf_code"
          size="small"
          scroll={{ x: 'max-content' }}
          pagination={false}
          onRow={(record) => ({
            onClick: () => navigate(`/etfs/${record.etf_code}`),
          })}
        />
      </Panel>
    </div>
  );
}
