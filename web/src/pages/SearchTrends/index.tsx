import { useMemo, useState, type ReactNode } from 'react';
import './styles.css';
import {
  Table, Input, Select, Button, Space, Tag, Skeleton, message, Tabs, Alert,
} from 'antd';
import { ReloadOutlined, SearchOutlined, FireOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import Panel from '@/components/Panel';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import EmptyState from '@/components/EmptyState';
import StatCard from '@/components/StatCard';
import LastUpdated from '@/components/LastUpdated';
import ThemeTag from '@/components/ThemeTag';
import { useDebounce } from '@/hooks/useDebounce';
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
    { title: '指数值', dataIndex: 'value', key: 'value', render: (v: number) => v.toLocaleString() },
    { title: '是否完整', dataIndex: 'is_partial', key: 'is_partial', width: 100, render: (v: boolean) => v ? <ThemeTag variant="warning">部分</ThemeTag> : <ThemeTag variant="success">完整</ThemeTag> },
  ];

  const compareColumns: ColumnsType<SearchTrend> = [
    { title: '日期', dataIndex: 'trade_date', key: 'trade_date', width: 110 },
    { title: '来源', dataIndex: 'source', key: 'source', width: 80, render: (v: string) => <ThemeTag variant={v === 'baidu' ? 'accent' : 'success'}>{v}</ThemeTag> },
    { title: '区域', dataIndex: 'region', key: 'region', width: 80 },
    { title: '指数值', dataIndex: 'value', key: 'value', render: (v: number) => v.toLocaleString() },
  ];

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
        <ResponsiveGrid cols={2} gap="md">
          <StatCard
            title="百度当日条目"
            value={dashboard?.baidu?.count ?? 0}
            icon={<FireOutlined />}
            suffix={dashboard?.baidu?.trade_date ? ` (${dashboard.baidu.trade_date})` : ''}
            loading={dashLoading}
          />
          <StatCard
            title="Google 当日条目"
            value={dashboard?.google?.count ?? 0}
            suffix={dashboard?.google?.trade_date ? ` (${dashboard.google.trade_date})` : ''}
            loading={dashLoading}
          />
        </ResponsiveGrid>
      </div>

      <div className="ad-mb-4">
        <ResponsiveGrid cols={1} gap="md">
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
                <Skeleton active />
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
                    <Skeleton active />
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
                    <Skeleton active />
                  ) : !compareData || compareData.series.length === 0 ? (
                    <EmptyState title="暂无该关键词数据" />
                  ) : (
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
          className="ad-list-row"
        >
          <Space>
            <ThemeTag variant={item.source === 'baidu' ? 'accent' : 'success'}>#{idx + 1}</ThemeTag>
            <span className="ad-font-medium">{item.keyword}</span>
            {item.category && <ThemeTag variant="neutral">{item.category}</ThemeTag>}
          </Space>
          <span className="font-mono">
            {item.value.toLocaleString()}
          </span>
        </div>
      ))}
    </div>
  );
}
