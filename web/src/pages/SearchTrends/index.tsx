import { useMemo, useState, type ReactNode } from 'react';
import './styles.css';
import {
  Table, Input, Select, Button, Space, Tag, message, Tabs, Alert,
} from 'antd';
import { ReloadOutlined, SearchOutlined, FireOutlined, GoogleOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import Panel from '@/components/Panel';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import EmptyState from '@/components/EmptyState';
import StatCard from '@/components/StatCard';
import LastUpdated from '@/components/LastUpdated';
import ThemeTag from '@/components/ThemeTag';
import LoadingBlock from '@/components/LoadingBlock';
import { useDebounce } from '@/hooks/useDebounce';
import { NULL_PLACEHOLDER } from '@/utils/format';
import {
  useSearchTrendList,
  useSearchTrendDashboard,
  useSearchTrendCompare,
  useRefreshSearchTrends,
} from '@/api/searchTrends';
import type { SearchTrend } from '@/api/searchTrends';

/**
 * Apple-style motion layer (scoped to this page):
 * - Response: feedback lands on pointer-down (:active, 0ms), release springs back.
 * - Springs: critically-damped-ish cubic-bezier; transform-only for frame smoothness.
 * - Typography: size-specific tracking (large tight, small loose).
 * - Reduced motion: cross-fade only, transforms disabled.
 */
const ADX_STYLE = `
.adx-search-trends {
  /* Critically-damped monotonic curve: y2 ≤ 1, no overshoot. */
  --adx-spring: cubic-bezier(0.32, 0.72, 0, 1);
  --adx-ease-out: cubic-bezier(0.22, 0.9, 0.3, 1);
}
.adx-search-trends .ant-btn {
  touch-action: manipulation;
  transition: transform 240ms var(--adx-spring), background-color 140ms var(--adx-ease-out);
}
.adx-search-trends .ant-btn:active {
  transform: scale(0.97);
  transition-duration: 0ms;
}
.adx-search-trends .ant-tabs-tab {
  touch-action: manipulation;
  transition: color 140ms var(--adx-ease-out);
}
.adx-search-trends .ant-select-selector {
  transition: border-color 140ms var(--adx-ease-out), box-shadow 140ms var(--adx-ease-out);
}
.adx-search-trends .ant-table-tbody > tr {
  transition: background-color 140ms var(--adx-ease-out);
}
.adx-search-trends h1,
.adx-search-trends h2,
.adx-search-trends .ant-typography h1,
.adx-search-trends .ant-typography h2 {
  letter-spacing: -0.02em;
  line-height: 1.18;
}
.adx-search-trends .ad-text-xs,
.adx-search-trends .ad-text-small {
  letter-spacing: 0.01em;
}
@media (prefers-reduced-motion: reduce) {
  .adx-search-trends *,
  .adx-search-trends *::before,
  .adx-search-trends *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }
  .adx-search-trends .ant-btn:active {
    transform: none;
  }
}
`;

function AdxShell({ children }: { children: ReactNode }) {
  return (
    <div className="adx-search-trends">
      <style>{ADX_STYLE}</style>
      {children}
    </div>
  );
}

const SOURCES = [
  { value: 'baidu', label: '百度' },
  { value: 'google', label: 'Google' },
];

const CATEGORIES = [
  { value: 'indices', label: '指数' },
  { value: 'stocks', label: '个股' },
  { value: 'macro', label: '宏观' },
];

/**
 * Baidu caps its index at 9999 — values ≥ 9999 are sentinel placeholders
 * for saturated rankings, not real heat, so render them as the null dash.
 */
function fmtTrendValue(v: number): string {
  return v >= 9999 ? NULL_PLACEHOLDER : v.toLocaleString();
}

export default function SearchTrendsPage() {
  const [tab, setTab] = useState('dashboard');
  const [source, setSource] = useState<string | undefined>();
  const [category, setCategory] = useState<string | undefined>();
  const [searchText, setSearchText] = useState<string>('');
  const [page, setPage] = useState(1);
  const [compareKeyword, setCompareKeyword] = useState<string | null>(null);

  // Debounce the text inputs that flow into React Query keys. Each input
  // fires a fresh request on every keystroke otherwise — coalescing into
  // 250 ms keeps the network/UI in sync without feeling laggy.
  const debouncedSearchText = useDebounce(searchText, 250);
  const debouncedCompareKeyword = useDebounce(compareKeyword, 250);

  const listParams = useMemo(
    () => ({
      page,
      page_size: 20,
      source,
      category,
      keyword: debouncedSearchText || undefined,
    }),
    [page, source, category, debouncedSearchText],
  );

  const { data: dashboard, dataUpdatedAt, isLoading: dashLoading } = useSearchTrendDashboard();
  const { data: listData, isLoading: listLoading } = useSearchTrendList(listParams);
  const { data: compareData, isLoading: compareLoading } = useSearchTrendCompare(debouncedCompareKeyword, 30);
  const refreshMutation = useRefreshSearchTrends();

  const handleRefresh = async () => {
    try {
      const res = await refreshMutation.mutateAsync();
      message.success(`搜索热度刷新完成: ${res.records} 条`);
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(`刷新失败: ${detail ?? '未知错误'}`);
    }
  };

  const listColumns: ColumnsType<SearchTrend> = [
    { title: '日期', dataIndex: 'trade_date', key: 'trade_date', width: 110 },
    { title: '来源', dataIndex: 'source', key: 'source', width: 80, render: (v: string) => <ThemeTag variant={v === 'baidu' ? 'accent' : 'success'}>{v}</ThemeTag> },
    { title: '区域', dataIndex: 'region', key: 'region', width: 80 },
    { title: '关键词', dataIndex: 'keyword', key: 'keyword', render: (v: string) => <Tag>{v}</Tag> },
    { title: '分类', dataIndex: 'category', key: 'category', width: 80, render: (v: string | null) => v ? <ThemeTag variant="neutral">{v}</ThemeTag> : '-' },
    { title: '指数值', dataIndex: 'value', key: 'value', render: (v: number) => fmtTrendValue(v) },
    { title: '是否完整', dataIndex: 'is_partial', key: 'is_partial', width: 100, render: (v: boolean) => v ? <ThemeTag variant="warning">部分</ThemeTag> : <ThemeTag variant="success">完整</ThemeTag> },
  ];

  const compareColumns: ColumnsType<SearchTrend> = [
    { title: '日期', dataIndex: 'trade_date', key: 'trade_date', width: 110 },
    { title: '来源', dataIndex: 'source', key: 'source', width: 80, render: (v: string) => <ThemeTag variant={v === 'baidu' ? 'accent' : 'success'}>{v}</ThemeTag> },
    { title: '区域', dataIndex: 'region', key: 'region', width: 80 },
    { title: '指数值', dataIndex: 'value', key: 'value', render: (v: number) => fmtTrendValue(v) },
  ];

  /* Dual-source trend chart: one line per source (baidu / google) across the
     compare window. The table below stays as the secondary detail view. */
  const compareChartOption: EChartsOption | null = useMemo(() => {
    if (!compareData || compareData.series.length === 0) return null;
    const dates = Array.from(new Set(compareData.series.map((s) => s.trade_date))).sort();
    const sources = Array.from(new Set(compareData.series.map((s) => s.source)));
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: sources },
      grid: { left: 60, right: 20, top: 40, bottom: 50 },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: { rotate: 45, fontSize: 10 },
      },
      yAxis: {
        type: 'value',
        name: '指数值',
        axisLabel: { fontSize: 11 },
      },
      series: sources.map((src) => ({
        name: src,
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: dates.map(
          (d) => compareData.series.find((s) => s.source === src && s.trade_date === d)?.value ?? null,
        ),
      })),
    };
  }, [compareData]);

  return (
    <AdxShell>
      <PageShell maxWidth="wide">
        <PageHeader
          title="搜索热度"
        description="百度热搜 + Google Trends 每日观察值。覆盖指数 / 个股 / 宏观关键词。每日 03:00 Asia/Shanghai 自动刷新。"
        extra={
          <Space>
            <LastUpdated at={dataUpdatedAt} />
            <Button
              type="primary"
              icon={<ReloadOutlined />}
              loading={refreshMutation.isPending}
              onClick={handleRefresh}
            >
              全量刷新
            </Button>
          </Space>
        }
      />

      <Alert
        type="info"
        showIcon
        message="数据仅供参考，非精确值"
        description="百度指数为搜索排名映射, Google Trends 为相对热度得分, 不同来源不可直接对比, 仅供趋势观察。"
        className="ad-mb-4"
      />

      <div className="ad-mb-4">
        <ResponsiveGrid cols={3} gap="md">
          <StatCard
            title="百度当日条目"
            value={dashboard?.baidu?.count ?? 0}
            icon={<FireOutlined />}
            loading={dashLoading}
          />
          <StatCard
            title="Google 当日条目"
            value={dashboard?.google?.count ?? 0}
            icon={<GoogleOutlined />}
            loading={dashLoading}
          />
          <StatCard
            title="最新观察日期"
            value={dashboard?.as_of ?? '-'}
            loading={dashLoading}
          />
        </ResponsiveGrid>
      </div>

      <Panel title="搜索热度">
        <Tabs
          activeKey={tab}
          onChange={setTab}
          items={[
            {
              key: 'dashboard',
              label: 'Top 关键词',
              children: dashLoading ? (
                <LoadingBlock size="md" />
              ) : (
                <ResponsiveGrid cols={2} gap="md">
                  <Panel title="百度热搜 Top 10" padding="sm">
                    <TopKeywordList items={dashboard?.baidu?.top_keywords ?? []} />
                  </Panel>
                  <Panel title="Google Trends Top 10" padding="sm">
                    <TopKeywordList items={dashboard?.google?.top_keywords ?? []} />
                  </Panel>
                </ResponsiveGrid>
              ),
            },
            {
              key: 'list',
              label: '历史明细',
              children: (
                <Space direction="vertical" className="ad-stack-full" size="middle">
                  <FilterToolbar total={listData?.total}>
                    <Select
                      placeholder="来源"
                      value={source}
                      onChange={setSource}
                      allowClear
                      className="ad-select--xxs"
                      options={SOURCES}
                    />
                    <Select
                      placeholder="分类"
                      value={category}
                      onChange={setCategory}
                      allowClear
                      className="ad-select--xxs"
                      options={CATEGORIES}
                    />
                    <Input
                      placeholder="搜索关键词"
                      value={searchText}
                      onChange={(e) => setSearchText(e.target.value)}
                      className="ad-input--md"
                      prefix={<SearchOutlined />}
                      allowClear
                    />
                  </FilterToolbar>
                  {listLoading ? (
                    <LoadingBlock size="md" />
                  ) : !listData || listData.items.length === 0 ? (
                    <EmptyState title="暂无搜索热度数据" />
                  ) : (
                    <div className="ad-table-scroll ad-table-sticky">
                      <Table
                        rowKey="id"
                        dataSource={listData.items}
                        columns={listColumns}
                        size="small"
                        scroll={{ x: 'max-content' }}
                        pagination={{
                          current: page,
                          pageSize: 20,
                          total: listData.total,
                          onChange: setPage,
                        }}
                      />
                    </div>
                  )}
                </Space>
              ),
            },
            {
              key: 'compare',
              label: '关键词对比',
              children: (
                <Space direction="vertical" className="ad-stack-full" size="middle">
                  <FilterToolbar>
                    <Input
                      placeholder="输入关键词 (如 上证指数)"
                      value={compareKeyword ?? ''}
                      onChange={(e) => setCompareKeyword(e.target.value || null)}
                      className="ad-input--lg"
                      prefix={<SearchOutlined />}
                      allowClear
                    />
                  </FilterToolbar>
                  {!compareKeyword ? (
                    <EmptyState title="请输入关键词以查看对比" />
                  ) : compareLoading ? (
                    <LoadingBlock size="md" />
                  ) : !compareData || compareData.series.length === 0 ? (
                    <EmptyState title="暂无该关键词数据" />
                  ) : (
                    <>
                      {compareChartOption && (
                        <div className="ad-chart-container">
                          <ReactECharts option={compareChartOption} notMerge />
                        </div>
                      )}
                      <div className="ad-table-scroll ad-table-sticky">
                        <Table
                          rowKey="id"
                          dataSource={compareData.series}
                          columns={compareColumns}
                          size="small"
                          scroll={{ x: 'max-content' }}
                          pagination={false}
                        />
                      </div>
                    </>
                  )}
                </Space>
              ),
            },
          ]}
        />
      </Panel>
      </PageShell>
    </AdxShell>
  );
}

function TopKeywordList({ items }: { items: SearchTrend[] }) {
  if (items.length === 0) {
    return <EmptyState title="暂无数据" />;
  }
  return (
    <div>
      {items.map((item, idx) => (
        <div
          key={item.id}
          className={`ad-list-row search-trends__keyword-row--${item.source}`}
        >
          <Space>
            {/* Rank badge stays neutral; the source colour is the left bar. */}
            <ThemeTag variant="neutral">#{idx + 1}</ThemeTag>
            <span className="ad-font-medium">{item.keyword}</span>
            {item.category && <ThemeTag variant="neutral">{item.category}</ThemeTag>}
          </Space>
          <span className="font-mono">
            {fmtTrendValue(item.value)}
          </span>
        </div>
      ))}
    </div>
  );
}
