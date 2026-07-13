import { useState, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Space, Select, InputNumber, Button, Row, Col } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useScreenResults, useScreenPresets, useScreenCategories } from '@/hooks/useScreenResults';
import { useScoreTemplates } from '@/hooks/useScores';
import { useInstrumentMarkets } from '@/hooks/useInstrumentList';
import { useScreenStore } from '@/stores/screen';
import { useAIHelp } from '@/hooks/useAIHelp';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { useDebounce } from '@/hooks/useDebounce';
import PageShell from '@/components/PageShell';
import Panel from '@/components/Panel';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import EmptyState from '@/components/EmptyState';
import HelpTrigger from '@/components/HelpTrigger';
import HelpPopover from '@/components/HelpPopover';
import { useSettingsStore } from '@/stores/settings';
import ContextHint from '@/components/ContextHint';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import ReturnTag from '@/components/ReturnTag';
import LastUpdated from '@/components/LastUpdated';
import { buildScreenContext } from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';

/** Map market codes to display labels */
const MARKET_LABELS: Record<string, string> = {
  'A股': 'A股',
  'US': '美股',
  'HK': '港股',
  'JP': '日股',
};


export default function Screen() {
  const navigate = useNavigate();
  const { open } = useAIHelp();
  const isMobile = useIsMobile();
  const mode = useSettingsStore((s) => s.mode);
  const { filters, preset, setFilter, resetFilters, applyPreset } = useScreenStore();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(isMobile ? 20 : 50);

  // Apple Design #1 Response: debounce InputNumber keystrokes so we don't
  // refire useScreenResults on every digit. Pagination and preset stay
  // immediate because they change discretely.
  const debouncedFilters = useDebounce(filters, 250);

  // Include pagination and active preset in API request
  const queryFilters = useMemo(
    () => ({
      ...debouncedFilters,
      ...(preset ? { preset } : {}),
      offset: (page - 1) * pageSize,
      limit: pageSize,
    }),
    [debouncedFilters, preset, page, pageSize]
  );
  const { data: results, isLoading, dataUpdatedAt: resultsUpdatedAt, isFetching: resultsFetching } = useScreenResults(queryFilters);
  const { data: presets } = useScreenPresets();
  const { data: categories } = useScreenCategories({ market: filters.market });
  const { data: markets } = useInstrumentMarkets();
  const { data: scoreTemplates } = useScoreTemplates();

  // Clear the selected category if it is not available in the current market.
  // Depend on filters.market so the effect re-evaluates when market changes,
  // even before the new categories query resolves.
  useEffect(() => {
    if (!filters.category || !categories) return;
    const available = categories.some((c: any) => c.category === filters.category);
    if (!available) {
      setFilter('category', undefined);
    }
  }, [categories, filters.category, filters.market, setFilter]);

  // Compute whether the category dropdown should be disabled.
  // A market may legitimately have zero ETFs in any category — disable the select
  // and show an explanatory hint instead of presenting an empty list.
  const categoryDisabled = !!(filters.market && categories && categories.length === 0);

  const handleOpenHelp = () => {
    open({
      pageType: 'screen',
      pageTitle: '全市场筛选器',
      contextData: buildScreenContext(filters, preset, results),
      quickQuestions: getQuickQuestions('screen'),
    });
  };

  const columns: ColumnsType<any> = [
    { title: '代码', dataIndex: 'code', width: 100, fixed: 'left', render: (v: string, r: any) => <InstrumentCodeTag code={v} name={r.name} name_zh={r.name_zh} /> },
    { title: '分类', dataIndex: 'category', width: 100, responsive: ['md'], render: (v: string) => v ? <span className="ad-table-text-secondary">{v}</span> : '-' },
    { title: <HelpPopover termKey="composite_score_filter" mode={mode}>评分</HelpPopover>, dataIndex: 'composite_score', width: 80, sorter: (a: any, b: any) => (a.composite_score ?? -Infinity) - (b.composite_score ?? -Infinity), render: (v: number) => <span className="font-mono ad-table-accent">{v?.toFixed(1)}</span> },
    { title: <HelpPopover termKey="rsi14" mode={mode}>RSI</HelpPopover>, dataIndex: 'rsi14', width: 70, responsive: ['md'], sorter: (a: any, b: any) => (a.rsi14 ?? -Infinity) - (b.rsi14 ?? -Infinity), render: (v: number) => <span className="font-mono ad-table-mono">{v?.toFixed(1)}</span> },
    { title: <HelpPopover termKey="sharpe_1y" mode={mode}>夏普</HelpPopover>, dataIndex: 'sharpe_1y', width: 80, responsive: ['md'], render: (v: number) => <span className="font-mono ad-table-mono">{v?.toFixed(2)}</span> },
    { title: <HelpPopover termKey="return_1m" mode={mode}>1月</HelpPopover>, dataIndex: 'return_1m', width: 100, sorter: (a: any, b: any) => (a.return_1m ?? -Infinity) - (b.return_1m ?? -Infinity), render: (v: number) => <ReturnTag value={v} /> },
    { title: <HelpPopover termKey="return_3m" mode={mode}>3月</HelpPopover>, dataIndex: 'return_3m', width: 100, responsive: ['md'], sorter: (a: any, b: any) => (a.return_3m ?? -Infinity) - (b.return_3m ?? -Infinity), render: (v: number) => <ReturnTag value={v} /> },
    { title: <HelpPopover termKey="return_1y" mode={mode}>1年</HelpPopover>, dataIndex: 'return_1y', width: 100, responsive: ['md'], sorter: (a: any, b: any) => (a.return_1y ?? -Infinity) - (b.return_1y ?? -Infinity), render: (v: number) => <ReturnTag value={v} /> },
    { title: <HelpPopover termKey="volatility_20d" mode={mode}>波动率</HelpPopover>, dataIndex: 'volatility_20d', width: 90, responsive: ['md'], render: (v: number) => v ? <span className="font-mono ad-table-mono">{v.toFixed(1)}%</span> : '-' },
  ];

  return (
    <PageShell maxWidth="wide">
      {/* Apple Design fixes:
          #1/#10 Response — clickable result rows give instant pointer-down
          feedback (background only, no movement).
          #4 Springs + #10 — preset chips keep the existing critically-damped
          (--ease-spring) curve for color/border feedback and rely on the
          global background active state; we deliberately drop the scale
          transform that was labelled "spring" but is in fact a one-shot
          cubic-bezier (no real spring solver running on every frame).
          #14 Reduced motion — chips keep color feedback, drop motion. */}
      <style>{`
        .screen-row--pressable > td { transition: background var(--transition-fast, 150ms ease); }
        .screen-row--pressable:active > td { background: var(--bg-active) !important; }
        .screen-presets .ad-status-chip {
          transition: background var(--transition-spring-fast),
            border-color var(--transition-fast, 150ms ease),
            color var(--transition-fast, 150ms ease);
        }
        @media (prefers-reduced-motion: reduce) {
          .screen-presets .ad-status-chip {
            transition: background var(--transition-fast, 150ms ease),
              border-color var(--transition-fast, 150ms ease),
              color var(--transition-fast, 150ms ease);
          }
        }
      `}</style>
      <PageHeader
        eyebrow="全市场"
        title="全市场筛选器"
        description="按评分、风险、收益、夏普等多维条件筛选全市场标的"
        extra={
          <Space size="middle">
            <LastUpdated at={resultsUpdatedAt} loading={resultsFetching && !results} />
            <HelpTrigger tooltip="AI 解释筛选逻辑" onClick={handleOpenHelp} />
          </Space>
        }
      />
      <Panel
        title="筛选条件"
        variant="default"
        extra={
          <Button onClick={() => { resetFilters(); setPage(1); }}>
            重置条件
          </Button>
        }
      >
        {/* 第一层：快速筛选 */}
        <section className="screen-filter-section" aria-label="快速筛选">
          <div className="screen-filter-section__header">
            <span className="screen-filter-section__title">
              <HelpPopover termKey="screen_presets" mode={mode}>快速筛选</HelpPopover>
            </span>
            <span className="screen-filter-section__hint">点击常用预设一键应用条件</span>
          </div>
          <div className="screen-presets">
            {presets?.map((p) => (
              <button
                key={p.key}
                className={`ad-status-chip ${preset === p.key ? 'ad-status-chip--active' : ''}`}
                onClick={() => applyPreset(preset === p.key ? null : p.key)}
                type="button"
                aria-pressed={preset === p.key}
              >
                {p.name}
              </button>
            ))}
          </div>
        </section>

        {/* 第二层：详细筛选条件 */}
        <ContextHint
          hintId="screen-filter"
          title="先选条件再查询"
          placement="bottom"
          content={
            <>
              选好市场 / 分类 / 评分阈值等条件后再点查询，比空着全部条件直接查能显著减少响应时间。结果表会用选股条件快速收敛到关注的几只标的。
            </>
          }
        >
          <FilterToolbar
            data-onboard="filter-toolbar"
            total={`共 ${results?.count || 0} 只`}
          >
            <div className="screen-filter-groups">
              {/* Group 1 — 基础：基础识别 (3 fields) */}
              <div className="screen-filter-group">
                <div className="screen-filter-group__title">基础</div>
                <Row gutter={[16, 12]}>
                  <Col xs={12} sm={8} md={6}>
                    <Select
                      placeholder="市场"
                      allowClear
                      className="ad-w-full"
                      value={filters.market}
                      options={(markets || []).map((m: string) => ({
                        label: MARKET_LABELS[m] || m,
                        value: m,
                      }))}
                      onChange={(v) => setFilter('market', v)}
                    />
                  </Col>
                  <Col xs={12} sm={8} md={6}>
                    <Select
                      placeholder={categoryDisabled ? '该市场暂无分类' : '分类'}
                      allowClear
                      className="ad-w-full"
                      value={filters.category}
                      disabled={categoryDisabled}
                      notFoundContent={
                        filters.market
                          ? `当前市场（${MARKET_LABELS[filters.market] || filters.market}）下无分类数据`
                          : '暂无可用分类'
                      }
                      options={categories?.map((c: any) => ({ label: `${c.category} (${c.count})`, value: c.category }))}
                      onChange={(v) => setFilter('category', v)}
                    />
                  </Col>
                  {scoreTemplates && scoreTemplates.length > 0 && (
                    <Col xs={12} sm={8} md={6}>
                      <Select
                        placeholder="评分模板"
                        allowClear
                        className="ad-w-full"
                        value={filters.template_id}
                        options={scoreTemplates.map((t) => ({
                          label: t.is_default ? `${t.name} (默认)` : t.name,
                          value: t.id,
                        }))}
                        onChange={(v) => setFilter('template_id', v)}
                      />
                    </Col>
                  )}
                </Row>
              </div>

              {/* Group 2 — 收益：1m / 3m / 1y 收益区间 (6 fields) */}
              <div className="screen-filter-group">
                <div className="screen-filter-group__title">收益</div>
                <Row gutter={[16, 12]}>
                  <Col xs={12} sm={8} md={6}>
                    <InputNumber
                      placeholder="1月 最小 (%)"
                      className="ad-w-full"
                      step={1}
                      value={filters.return_1m_min}
                      onChange={(v) => setFilter('return_1m_min', v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} sm={8} md={6}>
                    <InputNumber
                      placeholder="1月 最大 (%)"
                      className="ad-w-full"
                      step={1}
                      value={filters.return_1m_max}
                      onChange={(v) => setFilter('return_1m_max', v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} sm={8} md={6}>
                    <InputNumber
                      placeholder="3月 最小 (%)"
                      className="ad-w-full"
                      step={1}
                      value={filters.return_3m_min}
                      onChange={(v) => setFilter('return_3m_min', v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} sm={8} md={6}>
                    <InputNumber
                      placeholder="3月 最大 (%)"
                      className="ad-w-full"
                      step={1}
                      value={filters.return_3m_max}
                      onChange={(v) => setFilter('return_3m_max', v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} sm={8} md={6}>
                    <InputNumber
                      placeholder="1年 最小 (%)"
                      className="ad-w-full"
                      step={1}
                      value={filters.return_1y_min}
                      onChange={(v) => setFilter('return_1y_min', v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} sm={8} md={6}>
                    <InputNumber
                      placeholder="1年 最大 (%)"
                      className="ad-w-full"
                      step={1}
                      value={filters.return_1y_max}
                      onChange={(v) => setFilter('return_1y_max', v ?? undefined)}
                    />
                  </Col>
                </Row>
              </div>

              {/* Group 3 — 评分：评分 / RSI / 夏普 (6 fields) */}
              <div className="screen-filter-group">
                <div className="screen-filter-group__title">评分</div>
                <Row gutter={[16, 12]}>
                  <Col xs={12} sm={8} md={6}>
                    <InputNumber
                      placeholder="评分 最小"
                      className="ad-w-full"
                      min={0} max={100}
                      value={filters.score_min}
                      onChange={(v) => setFilter('score_min', v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} sm={8} md={6}>
                    <InputNumber
                      placeholder="评分 最大"
                      className="ad-w-full"
                      min={0} max={100}
                      value={filters.score_max}
                      onChange={(v) => setFilter('score_max', v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} sm={8} md={6}>
                    <InputNumber
                      placeholder="RSI 最小"
                      className="ad-w-full"
                      min={0} max={100}
                      value={filters.rsi_min}
                      onChange={(v) => setFilter('rsi_min', v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} sm={8} md={6}>
                    <InputNumber
                      placeholder="RSI 最大"
                      className="ad-w-full"
                      min={0} max={100}
                      value={filters.rsi_max}
                      onChange={(v) => setFilter('rsi_max', v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} sm={8} md={6}>
                    <InputNumber
                      placeholder="夏普 最小"
                      className="ad-w-full"
                      step={0.1}
                      value={filters.sharpe_min}
                      onChange={(v) => setFilter('sharpe_min', v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} sm={8} md={6}>
                    <InputNumber
                      placeholder="夏普 最大"
                      className="ad-w-full"
                      step={0.1}
                      value={filters.sharpe_max}
                      onChange={(v) => setFilter('sharpe_max', v ?? undefined)}
                    />
                  </Col>
                </Row>
              </div>

              {/* Group 4 — 风险：波动率 / 回撤 (4 fields) */}
              <div className="screen-filter-group">
                <div className="screen-filter-group__title">风险</div>
                <Row gutter={[16, 12]}>
                  <Col xs={12} sm={8} md={6}>
                    <InputNumber
                      placeholder="波动率 最小 (%)"
                      className="ad-w-full"
                      min={0}
                      step={0.1}
                      value={filters.volatility_min}
                      onChange={(v) => setFilter('volatility_min', v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} sm={8} md={6}>
                    <InputNumber
                      placeholder="波动率 最大 (%)"
                      className="ad-w-full"
                      min={0}
                      step={0.1}
                      value={filters.volatility_max}
                      onChange={(v) => setFilter('volatility_max', v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} sm={8} md={6}>
                    <InputNumber
                      placeholder="回撤1y 最小 (%)"
                      className="ad-w-full"
                      step={1}
                      value={filters.max_drawdown_1y_min}
                      onChange={(v) => setFilter('max_drawdown_1y_min', v ?? undefined)}
                    />
                  </Col>
                  <Col xs={12} sm={8} md={6}>
                    <InputNumber
                      placeholder="回撤1y 最大 (%)"
                      className="ad-w-full"
                      step={1}
                      value={filters.max_drawdown_1y_max}
                      onChange={(v) => setFilter('max_drawdown_1y_max', v ?? undefined)}
                    />
                  </Col>
                </Row>
              </div>
            </div>
          </FilterToolbar>
        </ContextHint>
      </Panel>

      <div className="ad-mt-5">
        {results?.items && results.items.length === 0 && !isLoading ? (
          <EmptyState
            title="暂无筛选结果"
            description="请调整筛选条件或重置后重试"
            action={
              <Button onClick={() => { resetFilters(); setPage(1); }}>
                重置条件
              </Button>
            }
          />
        ) : (
          <div className="ad-table-scroll ad-table-sticky">
            <Table
              dataSource={results?.items || []}
              columns={columns}
              rowKey="code"
              rowClassName="screen-row--pressable"
              loading={isLoading}
              pagination={{
                current: page,
                pageSize: pageSize,
                total: results?.count || 0,
                pageSizeOptions: [20, 50, 100, 200],
                showSizeChanger: true,
                showTotal: (total) => `共 ${total} 只`,
                onChange: (newPage, newSize) => {
                  setPage(newPage);
                  if (newSize !== pageSize) {
                    setPageSize(newSize);
                    setPage(1);
                  }
                },
              }}
              scroll={{ x: 'max-content' }}
              onRow={(record) => ({
                onClick: () => navigate(`/instruments/${record.code}`),
                // Apple Design #10 Agency: result rows must be operable by keyboard.
                tabIndex: 0,
                role: 'link',
                onKeyDown: (e: React.KeyboardEvent<HTMLElement>) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    navigate(`/instruments/${record.code}`);
                  }
                },
              })}
            />
          </div>
        )}
      </div>
    </PageShell>
  );
}
