import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Tabs } from 'antd';
import { useScores, useScoreTemplates } from '@/hooks/useScores';
import { useSparkline } from '@/hooks/useSparkline';
import { useAIHelp } from '@/hooks/useAIHelp';
import Panel from '@/components/Panel';
import HelpTrigger from '@/components/HelpTrigger';
import HelpPopover from '@/components/HelpPopover';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import ScoreBar from '@/components/ScoreBar';
import Sparkline from '@/components/Sparkline';
import TemplateManagement from '@/components/TemplateManagement';
import { buildScoreRankingContext } from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';

/** Row-level sparkline cell for scoring table.
 *  Uses the same backend sparkline endpoint as ETFList. */
function SparklineCell({ code }: { code: string }) {
  const { data } = useSparkline({ code, days: 7 });
  if (!data || !data.points || data.points.length === 0) {
    return <span style={{ color: 'var(--text-tertiary)', fontSize: 11 }}>-</span>;
  }
  return <Sparkline data={data.points} width={80} height={20} />;
}

type TopTab = 'ranking' | 'templates';

export default function ScoreRanking() {
  const navigate = useNavigate();
  const { open } = useAIHelp();
  const [topTab, setTopTab] = useState<TopTab>('ranking');
  const [templateId, setTemplateId] = useState<number | undefined>();
  const { data: scoresData } = useScores({ template_id: templateId, limit: 50 });
  const { data: templates } = useScoreTemplates();

  const activeTemplate = templates?.find((t) =>
    templateId ? t.id === templateId : t.is_default,
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
        <span style={{ fontWeight: 500, color: v <= 3 ? 'var(--accent)' : 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
          {v}
        </span>
      ),
    },
    {
      title: <HelpPopover termKey="rank_category">分类排名</HelpPopover>,
      dataIndex: 'rank_category',
      width: 90,
      render: (v: number) => <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)' }}>{v}</span>,
    },
    {
      title: '标的',
      render: (_: unknown, record: any) => <InstrumentCodeTag code={record.etf_code} name={record.etf_name} />,
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
    {
      title: '近 7 日',
      key: 'sparkline_7d',
      width: 100,
      render: (_: unknown, record: any) => <SparklineCell code={record.etf_code} />,
    },
  ];

  const templateTabItems = templates?.map((t) => ({
    key: String(t.id),
    label: t.name,
  })) || [];

  return (
    <div>
      <h1 style={{ fontSize: 'var(--text-h1-size)', fontWeight: 500, color: 'var(--text-primary)', margin: '0 0 8px', letterSpacing: '-0.03em' }}>评分排名</h1>
      <p style={{ margin: '0 0 32px', color: 'var(--text-tertiary)', fontSize: 'var(--text-body-size)' }}>查看全市场标的综合评分排名，对比不同模板下的多维评估结果</p>

      <Tabs
        activeKey={topTab}
        onChange={(k) => setTopTab(k as TopTab)}
        style={{ marginBottom: 20 }}
        items={[
          { key: 'ranking', label: '排名' },
          { key: 'templates', label: '模板管理' },
        ]}
      />

      {topTab === 'ranking' && (
        <>
          <Panel variant="minimal" style={{ marginBottom: 20 }}>
            <Tabs
              activeKey={String(templateId || templates?.find((t) => t.is_default)?.id || '')}
              onChange={(key) => setTemplateId(Number(key))}
              items={templateTabItems}
              style={{ marginBottom: 0 }}
            />
          </Panel>

          <Panel
            variant="minimal"
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
        </>
      )}

      {topTab === 'templates' && <TemplateManagement />}
    </div>
  );
}
