import './styles.css';

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Table, List, Tabs, Segmented, Select } from 'antd';
import { useScores, useScoreTemplates } from '@/hooks/useScores';
import { useAIHelp } from '@/hooks/useAIHelp';
import { useIsMobile } from '@/hooks/useBreakpoint';
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
import { FilterSheetButton } from '@/components/BottomSheet';
import ScoreBar from '@/components/ScoreBar';
import TemplateManagement from '@/components/TemplateManagement';
import PageHeader from '@/components/PageHeader';
import LastUpdated from '@/components/LastUpdated';
import { clickableRow } from '@/utils/a11y';
import { buildScoreRankingContext } from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';

type TopTab = 'ranking' | 'templates';

/** 市场筛选：'all' 不传参；cn_a / us 由后端映射为 A股 / US。数字币暂不纳入排名。 */
type MarketFilter = 'all' | 'cn_a' | 'us';
/** 类型筛选：'all' 不传参；STOCK=个股 / ETF。 */
type TypeFilter = 'all' | 'STOCK' | 'ETF';

const MARKET_OPTIONS: { value: MarketFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'cn_a', label: 'A股' },
  { value: 'us', label: '美股' },
];

const TYPE_OPTIONS: { value: TypeFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'STOCK', label: '个股' },
  { value: 'ETF', label: 'ETF' },
];

export default function ScoreRanking() {
  const navigate = useNavigate();
  const { open } = useAIHelp();
  const isMobile = useIsMobile();
  const mode = useSettingsStore((s) => s.mode);
  const [topTab, setTopTab] = useState<TopTab>('ranking');
  const [templateId, setTemplateId] = useState<number | undefined>();
  const [marketFilter, setMarketFilter] = useState<MarketFilter>('all');
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all');
  const { data: scoresData, dataUpdatedAt: scoresUpdatedAt, isFetching } = useScores({
    template_id: templateId,
    market: marketFilter === 'all' ? undefined : marketFilter,
    instrument_type: typeFilter === 'all' ? undefined : typeFilter,
    limit: 50,
  });
  const { data: templates } = useScoreTemplates();

  const activeTemplate = templates?.find((t) =>
    templateId ? t.id === templateId : t.is_default,
  );

  const activeTemplateKey = String(templateId || templates?.find((t) => t.is_default)?.id || '');
  const templateOptions = templates?.map((t) => ({ value: String(t.id), label: t.name })) || [];

  // Mean composite score of the visible slice — always has a value when
  // items exist, unlike the old "榜首收益得分" card which could read 0.0.
  const avgScore =
    scoresData?.items && scoresData.items.length > 0
      ? scoresData.items.reduce((sum: number, it: any) => sum + (it.composite_score ?? 0), 0) /
        scoresData.items.length
      : undefined;

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
      // Wide enough for 5-char title + sorter + help icon on one line.
      width: 132,
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
      // Wide enough for 4-char title + sorter + help icon on one line.
      width: 116,
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

  return (
    <PageShell maxWidth="wide">
      {/* Apple Design fixes:
          #1/#10 Response — clickable ranking rows give instant pointer-down
          feedback (background only, no movement).
          #15 Typography — large summary numbers get size-specific negative
          tracking (data figures read tighter at display sizes). The name
          variant keeps default tracking so labels read normally. */}
      <style>{`
        .score-ranking-row--pressable > td { transition: background var(--transition-fast, 150ms ease); }
        .score-ranking-row--pressable:active > td { background: var(--bg-active) !important; }
        /* Scope negative tracking to the numeric large variant only; the
           name/large-text variant keeps default tracking so labels read
           comfortably. */
        .score-summary-card__value:not(.score-summary-card__value--name) { letter-spacing: var(--tracking-data, -0.02em); }
      `}</style>
      <PageHeader
        eyebrow="评分"
        title="评分排名"
        description="查看全市场标的综合评分排名，对比不同模板下的多维评估结果"
        extra={<LastUpdated at={scoresUpdatedAt} loading={isFetching && !scoresData} />}
      />
      {/* P1-2 互跳引导（2026-08-02 IA 调整）：评分排名 ↔ 全市场筛选器 */}
      <div className="ad-mb-3" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
        想自定义区间？<Link to="/screen">全市场筛选器 →</Link>
      </div>

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
                  <div className="score-summary-card__label">平均评分</div>
                  <div className="tabular-nums score-summary-card__value">
                    {avgScore?.toFixed(1) ?? '—'}
                  </div>
                  <div className="score-summary-card__sub">
                    Top {scoresData.items.length} 均值 · 满分 100
                  </div>
                </Panel>
              </ResponsiveGrid>
            </section>
          )}

          <SectionHeading
            title={`综合评分 Top ${scoresData?.items.length || 0}`}
            action={
              isMobile ? (
                /* P3 (方向 C): the template picker moves into a sheet on
                   mobile so the Segmented can never wrap/overflow. The
                   market / type filters live in the same sheet. */
                <FilterSheetButton
                  title="筛选与模板"
                  buttonText="筛选"
                  activeCount={
                    (marketFilter !== 'all' ? 1 : 0) +
                    (typeFilter !== 'all' ? 1 : 0) +
                    (templateId ? 1 : 0)
                  }
                  snaps={['peek', 'half']}
                >
                  <div className="ad-text-small ad-text-tertiary">市场</div>
                  <Select
                    aria-label="市场"
                    className="ad-w-full"
                    value={marketFilter}
                    onChange={(v) => setMarketFilter(v as MarketFilter)}
                    options={MARKET_OPTIONS}
                  />
                  <div className="ad-text-small ad-text-tertiary">类型</div>
                  <Select
                    aria-label="类型"
                    className="ad-w-full"
                    value={typeFilter}
                    onChange={(v) => setTypeFilter(v as TypeFilter)}
                    options={TYPE_OPTIONS}
                  />
                  <div className="ad-text-small ad-text-tertiary">评分模板</div>
                  <Select
                    aria-label="评分模板"
                    className="ad-w-full"
                    value={activeTemplateKey}
                    onChange={(key) => setTemplateId(Number(key))}
                    options={templateOptions}
                  />
                  {activeTemplate && (
                    <div className="ad-text-small ad-text-tertiary">
                      {Object.keys(activeTemplate.weights ?? {}).length} 个维度
                    </div>
                  )}
                </FilterSheetButton>
              ) : (
                <div className="ad-flex ad-items-center ad-gap-2 score-ranking-filters">
                  <span className="ad-text-small ad-text-tertiary">市场</span>
                  <Segmented
                    aria-label="市场"
                    value={marketFilter}
                    onChange={(v) => setMarketFilter(v as MarketFilter)}
                    options={MARKET_OPTIONS}
                  />
                  <span className="ad-text-small ad-text-tertiary">类型</span>
                  <Segmented
                    aria-label="类型"
                    value={typeFilter}
                    onChange={(v) => setTypeFilter(v as TypeFilter)}
                    options={TYPE_OPTIONS}
                  />
                  <span className="ad-text-small ad-text-tertiary">模板</span>
                  <Segmented
                    aria-label="评分模板"
                    value={activeTemplateKey}
                    onChange={(key) => setTemplateId(Number(key))}
                    options={templateOptions}
                  />
                </div>
              )
            }
          />

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
            {isMobile ? (
              /* 移动端：hairline 行式列表（density token 几何）。
                 主信息 = 排名 + 代码/名称，右侧 = 近7日 sparkline +
                 综合评分；次行 = 收益/风险/夏普 次级分。整行可点进详情。 */
              <List
                className="ad-list-compact mobile-list"
                dataSource={scoresData?.items || []}
                renderItem={(record: any) => (
                  <div
                    role="button"
                    tabIndex={0}
                    aria-label={`查看 ${record.etf_name || record.etf_code} 详情`}
                    className="mobile-list-item"
                    onClick={() => navigate(`/instruments/${record.etf_code}`)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        navigate(`/instruments/${record.etf_code}`);
                      }
                    }}
                  >
                    <div className="mobile-list-item__row">
                      <div className="mobile-list-item__main ad-flex ad-items-center ad-gap-2">
                        <span
                          className={`tabular-nums score-rank-cell ${
                            record.rank_overall <= 3
                              ? 'score-rank-cell--top3'
                              : 'score-rank-cell--normal'
                          }`}
                        >
                          {record.rank_overall}
                        </span>
                        <InstrumentCodeTag
                          code={record.etf_code}
                          name={record.etf_name}
                          name_zh={record.name_zh}
                        />
                      </div>
                      <div className="mobile-list-item__metrics">
                        <SparklineCell code={record.etf_code} days={7} />
                        <span className="tabular-nums mobile-list-item__value ad-text-accent">
                          {record.composite_score?.toFixed(1) ?? '—'}
                        </span>
                      </div>
                    </div>
                    <div className="mobile-list-item__tags">
                      {record.score_return != null && (
                        <span className="tabular-nums mobile-list-item__meta">
                          收益 {record.score_return.toFixed(1)}
                        </span>
                      )}
                      {record.score_risk != null && (
                        <span className="tabular-nums mobile-list-item__meta">
                          风险 {record.score_risk.toFixed(1)}
                        </span>
                      )}
                      {record.score_sharpe != null && (
                        <span className="tabular-nums mobile-list-item__meta">
                          夏普 {record.score_sharpe.toFixed(1)}
                        </span>
                      )}
                      {record.score_liquidity != null && (
                        <span className="tabular-nums mobile-list-item__meta">
                          流动性 {record.score_liquidity.toFixed(1)}
                        </span>
                      )}
                      {record.score_trend != null && (
                        <span className="tabular-nums mobile-list-item__meta">
                          趋势 {record.score_trend.toFixed(1)}
                        </span>
                      )}
                    </div>
                  </div>
                )}
                pagination={{
                  pageSize: 20,
                  size: 'small',
                  showSizeChanger: false,
                  className: 'mobile-list-pagination',
                }}
                locale={{
                  emptyText: <EmptyState title="暂无数据" />,
                }}
              />
            ) : (
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
                onRow={(record) => clickableRow(() => navigate(`/instruments/${record.etf_code}`))}
              />
            </div>
            )}
          </Panel>
        </>
      )}

      {topTab === 'templates' && <TemplateManagement />}
    </PageShell>
  );
}
