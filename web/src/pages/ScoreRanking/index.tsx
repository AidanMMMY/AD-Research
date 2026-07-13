import './styles.css';

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Tabs } from 'antd';
import { useScores, useScoreTemplates } from '@/hooks/useScores';
import { useAIHelp } from '@/hooks/useAIHelp';
import { useSettingsStore } from '@/stores/settings';
import SparklineCell from '@/components/SparklineCell';
import PageShell from '@/components/PageShell';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import Panel from '@/components/Panel';
import SectionHeading from '@/components/SectionHeading';
import EmptyState from '@/components/EmptyState';
import HelpTrigger from '@/components/HelpTrigger';
import HelpPopover from '@/components/HelpPopover';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import ScoreBar from '@/components/ScoreBar';
import TemplateManagement from '@/components/TemplateManagement';
import PageHeader from '@/components/PageHeader';
import LastUpdated from '@/components/LastUpdated';
import { buildScoreRankingContext } from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';

type TopTab = 'ranking' | 'templates';

export default function ScoreRanking() {
  const navigate = useNavigate();
  const { open } = useAIHelp();
  const mode = useSettingsStore((s) => s.mode);
  const [topTab, setTopTab] = useState<TopTab>('ranking');
  const [templateId, setTemplateId] = useState<number | undefined>();
  const { data: scoresData, dataUpdatedAt: scoresUpdatedAt, isFetching } = useScores({ template_id: templateId, limit: 50 });
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

  const tableWrapClass = 'ad-table-scroll ad-table-sticky';

  const columns = [
    {
      title: <HelpPopover termKey="rank_overall" mode={mode}>全市场排名</HelpPopover>,
      dataIndex: 'rank_overall',
      width: 90,
      sorter: (a: any, b: any) => (a.rank_overall ?? Infinity) - (b.rank_overall ?? Infinity),
      render: (v: number) => (
        <span className={`tabular-nums score-rank-cell ${v <= 3 ? 'score-rank-cell--top3' : 'score-rank-cell--normal'}`}>
          {v}
        </span>
      ),
    },
    {
      title: <HelpPopover termKey="rank_category" mode={mode}>分类排名</HelpPopover>,
      dataIndex: 'rank_category',
      width: 90,
      responsive: ['md'] as ('md' | 'lg' | 'xl' | 'xxl')[],
      sorter: (a: any, b: any) => (a.rank_category ?? Infinity) - (b.rank_category ?? Infinity),
      render: (v: number) => <span className="tabular-nums font-mono ad-text-tertiary">{v}</span>,
    },
    {
      title: '标的',
      render: (_: unknown, record: any) => <InstrumentCodeTag code={record.etf_code} name={record.etf_name} name_zh={record.name_zh} />,
    },
    {
      title: <HelpPopover termKey="composite_score" mode={mode}>综合评分</HelpPopover>,
      sorter: (a: any, b: any) => (a.composite_score ?? -Infinity) - (b.composite_score ?? -Infinity),
      render: (_: unknown, record: any) => <ScoreBar score={record.composite_score} />,
      width: 180,
    },
    { title: <HelpPopover termKey="score_return" mode={mode}>收益</HelpPopover>, dataIndex: 'score_return', width: 80, sorter: (a: any, b: any) => (a.score_return ?? -Infinity) - (b.score_return ?? -Infinity), render: (v: number) => <span className="tabular-nums font-mono ad-text-secondary">{v?.toFixed(1)}</span> },
    { title: <HelpPopover termKey="score_risk" mode={mode}>风险</HelpPopover>, dataIndex: 'score_risk', width: 80, sorter: (a: any, b: any) => (a.score_risk ?? -Infinity) - (b.score_risk ?? -Infinity), render: (v: number) => <span className="tabular-nums font-mono ad-text-secondary">{v?.toFixed(1)}</span> },
    { title: <HelpPopover termKey="score_sharpe" mode={mode}>夏普</HelpPopover>, dataIndex: 'score_sharpe', width: 80, responsive: ['md'] as ('md' | 'lg' | 'xl' | 'xxl')[], sorter: (a: any, b: any) => (a.score_sharpe ?? -Infinity) - (b.score_sharpe ?? -Infinity), render: (v: number) => <span className="tabular-nums font-mono ad-text-secondary">{v?.toFixed(1)}</span> },
    { title: <HelpPopover termKey="score_liquidity" mode={mode}>流动性</HelpPopover>, dataIndex: 'score_liquidity', width: 90, responsive: ['md'] as ('md' | 'lg' | 'xl' | 'xxl')[], sorter: (a: any, b: any) => (a.score_liquidity ?? -Infinity) - (b.score_liquidity ?? -Infinity), render: (v: number) => <span className="tabular-nums font-mono ad-text-secondary">{v?.toFixed(1)}</span> },
    { title: <HelpPopover termKey="score_trend" mode={mode}>趋势</HelpPopover>, dataIndex: 'score_trend', width: 80, responsive: ['md'] as ('md' | 'lg' | 'xl' | 'xxl')[], sorter: (a: any, b: any) => (a.score_trend ?? -Infinity) - (b.score_trend ?? -Infinity), render: (v: number) => <span className="tabular-nums font-mono ad-text-secondary">{v?.toFixed(1)}</span> },
    {
      title: '近 7 日',
      key: 'sparkline_7d',
      width: 100,
      render: (_: unknown, record: any) => <SparklineCell code={record.etf_code} days={7} />,
    },
  ];

  const templateTabItems = templates?.map((t) => ({
    key: String(t.id),
    label: t.name,
  })) || [];

  return (
    <PageShell maxWidth="wide">
      {/* Apple Design fixes:
          #1/#10 Response — clickable ranking rows give instant pointer-down
          feedback (background only, no movement).
          #15 Typography — large summary numbers get size-specific negative
          tracking (data figures read tighter at display sizes). */}
      <style>{`
        .score-ranking-row--pressable > td { transition: background var(--transition-fast, 150ms ease); }
        .score-ranking-row--pressable:active > td { background: var(--bg-active) !important; }
        .score-summary-card__value { letter-spacing: var(--tracking-data, -0.02em); }
      `}</style>
      <PageHeader
        eyebrow="评分"
        title="评分排名"
        description="查看全市场标的综合评分排名，对比不同模板下的多维评估结果"
        extra={<LastUpdated at={scoresUpdatedAt} loading={isFetching && !scoresData} />}
      />

      <Tabs
        activeKey={topTab}
        onChange={(k) => setTopTab(k as TopTab)}
        className="ad-mb-5"
        items={[
          { key: 'ranking', label: '排名' },
          { key: 'templates', label: '模板管理' },
        ]}
      />

      {topTab === 'ranking' && (
        <>
          {scoresData?.items && scoresData.items.length > 0 && (
            <section className="dashboard-section">
              <SectionHeading title="评分总览" />
              <ResponsiveGrid cols={4} gap="md">
                <Panel variant="default" className="score-summary-card">
                  <div className="score-summary-card__label">榜首标的</div>
                  <InstrumentCodeTag code={scoresData.items[0].etf_code} name={scoresData.items[0].etf_name} name_zh={scoresData.items[0].name_zh} />
                  <div className="tabular-nums score-summary-card__value score-summary-card__value--spaced">
                    {scoresData.items[0].composite_score?.toFixed(1) ?? '—'}
                  </div>
                </Panel>

                <Panel variant="default" className="score-summary-card">
                  <div className="score-summary-card__label">使用模板</div>
                  <div className="score-summary-card__value score-summary-card__value--name">
                    {activeTemplate?.name ?? '默认'}
                  </div>
                  <div className="score-summary-card__sub">
                    {activeTemplate ? `${Object.keys(activeTemplate.weights ?? {}).length} 个维度` : '系统内置'}
                  </div>
                </Panel>

                <Panel variant="default" className="score-summary-card">
                  <div className="score-summary-card__label">排名数量</div>
                  <div className="tabular-nums score-summary-card__value">
                    {scoresData.items.length}
                  </div>
                  <div className="score-summary-card__sub">
                    当前页 Top {scoresData.items.length}
                  </div>
                </Panel>

                <Panel variant="default" className="score-summary-card">
                  <div className="score-summary-card__label">榜首收益得分</div>
                  <div className="tabular-nums score-summary-card__value">
                    {scoresData.items[0].score_return?.toFixed(1) ?? '—'}
                  </div>
                  <div className="score-summary-card__sub">
                    满分 100
                  </div>
                </Panel>
              </ResponsiveGrid>
            </section>
          )}

          <Panel variant="default" padding="none" className="ad-mb-5">
            <Tabs
              activeKey={String(templateId || templates?.find((t) => t.is_default)?.id || '')}
              onChange={(key) => setTemplateId(Number(key))}
              items={templateTabItems}
              className="ad-mb-0"
            />
          </Panel>

          <SectionHeading title={`综合评分 Top ${scoresData?.items.length || 0}`} />

          <Panel
            variant="default"
            padding="md"
            extra={
              <HelpTrigger
                tooltip="AI 解释评分逻辑"
                onClick={handleOpenHelp}
              />
            }
          >
            <div className={tableWrapClass}>
              <Table
                dataSource={scoresData?.items || []}
                columns={columns}
                rowKey="etf_code"
                size="small"
                rowClassName="score-ranking-row--pressable"
                scroll={{ x: 'max-content' }}
                pagination={false}
                locale={{
                  emptyText: <EmptyState title="暂无数据" />,
                }}
                onRow={(record) => ({
                  onClick: () => navigate(`/instruments/${record.etf_code}`),
                })}
              />
            </div>
          </Panel>
        </>
      )}

      {topTab === 'templates' && <TemplateManagement />}
    </PageShell>
  );
}
