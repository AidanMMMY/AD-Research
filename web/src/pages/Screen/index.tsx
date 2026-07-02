import { useState, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Space, Select, InputNumber, Button, Row, Col } from 'antd';
import { useScreenResults, useScreenPresets, useScreenCategories } from '@/hooks/useScreenResults';
import { useInstrumentMarkets } from '@/hooks/useInstrumentList';
import { useScreenStore } from '@/stores/screen';
import { useAIHelp } from '@/hooks/useAIHelp';
import PageShell from '@/components/PageShell';
import Panel from '@/components/Panel';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import EmptyState from '@/components/EmptyState';
import HelpTrigger from '@/components/HelpTrigger';
import HelpPopover from '@/components/HelpPopover';
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
  const { filters, preset, setFilter, resetFilters, applyPreset } = useScreenStore();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  // Include pagination and active preset in API request
  const queryFilters = useMemo(
    () => ({
      ...filters,
      ...(preset ? { preset } : {}),
      offset: (page - 1) * pageSize,
      limit: pageSize,
    }),
    [filters, preset, page, pageSize]
  );
  const { data: results, isLoading, dataUpdatedAt: resultsUpdatedAt, isFetching: resultsFetching } = useScreenResults(queryFilters);
  const { data: presets } = useScreenPresets();
  const { data: categories } = useScreenCategories({ market: filters.market });
  const { data: markets } = useInstrumentMarkets();

  // Clear the selected category if it is not available in the current market.
  useEffect(() => {
    if (filters.category && categories) {
      const available = categories.some((c: any) => c.category === filters.category);
      if (!available) {
        setFilter('category', undefined);
      }
    }
  }, [categories, filters.category, setFilter]);

  const handleOpenHelp = () => {
    open({
      pageType: 'screen',
      pageTitle: '全市场筛选器',
      contextData: buildScreenContext(filters, preset, results),
      quickQuestions: getQuickQuestions('screen'),
    });
  };

  const columns = [
    { title: '代码', dataIndex: 'code', width: 100, render: (v: string, r: any) => <InstrumentCodeTag code={v} name={r.name} /> },
    { title: '分类', dataIndex: 'category', width: 100, render: (v: string) => v ? <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-secondary)' }}>{v}</span> : '-' },
    { title: <HelpPopover termKey="composite_score_filter">评分</HelpPopover>, dataIndex: 'composite_score', width: 80, render: (v: number) => <span className="font-mono" style={{ fontWeight: 700, color: 'var(--accent)' }}>{v?.toFixed(1)}</span> },
    { title: <HelpPopover termKey="rsi14">RSI</HelpPopover>, dataIndex: 'rsi14', width: 70, render: (v: number) => <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>{v?.toFixed(1)}</span> },
    { title: <HelpPopover termKey="sharpe_1y">夏普</HelpPopover>, dataIndex: 'sharpe_1y', width: 80, render: (v: number) => <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>{v?.toFixed(2)}</span> },
    { title: <HelpPopover termKey="return_1m">1月</HelpPopover>, dataIndex: 'return_1m', width: 100, render: (v: number) => <ReturnTag value={v} /> },
    { title: <HelpPopover termKey="return_3m">3月</HelpPopover>, dataIndex: 'return_3m', width: 100, render: (v: number) => <ReturnTag value={v} /> },
    { title: <HelpPopover termKey="return_1y">1年</HelpPopover>, dataIndex: 'return_1y', width: 100, render: (v: number) => <ReturnTag value={v} /> },
    { title: <HelpPopover termKey="volatility_20d">波动率</HelpPopover>, dataIndex: 'volatility_20d', width: 90, render: (v: number) => v ? <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>{v.toFixed(1)}%</span> : '-' },
  ];

  return (
    <PageShell maxWidth="wide">
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
      <Panel title="筛选条件" variant="default">
        <div className="ad-filter-label">
          <HelpPopover termKey="screen_presets">快速筛选</HelpPopover>:
        </div>
        <div className="ad-flex ad-flex-wrap ad-gap-2 ad-mb-4">
          {presets?.map((p) => (
            <button
              key={p.key}
              className={`ad-status-chip ${preset === p.key ? 'ad-status-chip--active' : ''}`}
              onClick={() => applyPreset(preset === p.key ? null : p.key)}
              type="button"
            >
              {p.name}
            </button>
          ))}
        </div>

        <FilterToolbar
          total={`共 ${results?.count || 0} 只`}
          extra={
            <Button onClick={() => { resetFilters(); setPage(1); }}>
              重置条件
            </Button>
          }
        >
          <Row gutter={[16, 12]}>
            <Col xs={12} sm={8} md={6}>
              <Select
                placeholder="市场"
                allowClear
                style={{ width: '100%' }}
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
                placeholder="分类"
                allowClear
                style={{ width: '100%' }}
                value={filters.category}
                options={categories?.map((c: any) => ({ label: `${c.category} (${c.count})`, value: c.category }))}
                onChange={(v) => setFilter('category', v)}
              />
            </Col>
            <Col xs={12} sm={8} md={6}>
              <InputNumber
                placeholder="评分最小"
                style={{ width: '100%' }}
                min={0} max={100}
                value={filters.score_min}
                onChange={(v) => setFilter('score_min', v || undefined)}
              />
            </Col>
            <Col xs={12} sm={8} md={6}>
              <InputNumber
                placeholder="RSI最小"
                style={{ width: '100%' }}
                min={0} max={100}
                value={filters.rsi_min}
                onChange={(v) => setFilter('rsi_min', v || undefined)}
              />
            </Col>
            <Col xs={12} sm={8} md={6}>
              <InputNumber
                placeholder="夏普最小"
                style={{ width: '100%' }}
                value={filters.sharpe_min}
                onChange={(v) => setFilter('sharpe_min', v || undefined)}
              />
            </Col>
            <Col xs={12} sm={8} md={6}>
              <InputNumber
                placeholder="波动率最大"
                style={{ width: '100%' }}
                value={filters.volatility_max}
                onChange={(v) => setFilter('volatility_max', v || undefined)}
              />
            </Col>
          </Row>
        </FilterToolbar>
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
          <div className="ad-density-dense ad-table-scroll ad-table-sticky">
            <Table
              dataSource={results?.items || []}
              columns={columns}
              rowKey="code"
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
                onClick: () => navigate(`/etfs/${record.code}`),
              })}
            />
          </div>
        )}
      </div>
    </PageShell>
  );
}
