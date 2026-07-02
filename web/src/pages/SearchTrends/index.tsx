import { useMemo, useState } from 'react';
import {
  Table, Input, Select, Button, Space, Tag, Skeleton, message, Empty, Row, Col, Statistic, Card, Tabs, Alert,
} from 'antd';
import { ReloadOutlined, SearchOutlined, FireOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import LastUpdated from '@/components/LastUpdated';
import {
  useSearchTrendList,
  useSearchTrendDashboard,
  useSearchTrendCompare,
  useRefreshSearchTrends,
} from '@/api/searchTrends';
import type { SearchTrend } from '@/api/searchTrends';

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

  const listParams = useMemo(
    () => ({
      page,
      page_size: 20,
      source,
      category,
      keyword: searchText || undefined,
    }),
    [page, source, category, searchText],
  );

  const { data: dashboard, dataUpdatedAt, isLoading: dashLoading } = useSearchTrendDashboard();
  const { data: listData, isLoading: listLoading } = useSearchTrendList(listParams);
  const { data: compareData, isLoading: compareLoading } = useSearchTrendCompare(compareKeyword, 30);
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
    { title: '来源', dataIndex: 'source', key: 'source', width: 80, render: (v: string) => <Tag color={v === 'baidu' ? 'blue' : 'green'}>{v}</Tag> },
    { title: '区域', dataIndex: 'region', key: 'region', width: 80 },
    { title: '关键词', dataIndex: 'keyword', key: 'keyword', render: (v: string) => <Tag>{v}</Tag> },
    { title: '分类', dataIndex: 'category', key: 'category', width: 80, render: (v: string | null) => v ? <Tag color="purple">{v}</Tag> : '-' },
    { title: '指数值', dataIndex: 'value', key: 'value', render: (v: number) => v.toLocaleString() },
    { title: '是否完整', dataIndex: 'is_partial', key: 'is_partial', width: 100, render: (v: boolean) => v ? <Tag color="gold">部分</Tag> : <Tag color="green">完整</Tag> },
  ];

  const compareColumns: ColumnsType<SearchTrend> = [
    { title: '日期', dataIndex: 'trade_date', key: 'trade_date', width: 110 },
    { title: '来源', dataIndex: 'source', key: 'source', width: 80, render: (v: string) => <Tag color={v === 'baidu' ? 'blue' : 'green'}>{v}</Tag> },
    { title: '区域', dataIndex: 'region', key: 'region', width: 80 },
    { title: '指数值', dataIndex: 'value', key: 'value', render: (v: number) => v.toLocaleString() },
  ];

  return (
    <div style={{ padding: '0 0 24px' }}>
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
        style={{ marginBottom: 16 }}
      />

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="百度当日条目"
              value={dashboard?.baidu?.count ?? 0}
              prefix={<FireOutlined />}
              suffix={dashboard?.baidu?.trade_date ? ` (${dashboard.baidu.trade_date})` : ''}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="Google 当日条目"
              value={dashboard?.google?.count ?? 0}
              suffix={dashboard?.google?.trade_date ? ` (${dashboard.google.trade_date})` : ''}
            />
          </Card>
        </Col>
        <Col xs={12} md={12}>
          <Card>
            <Statistic
              title="最新观察日期"
              value={dashboard?.as_of ?? '-'}
              valueStyle={{ fontSize: 18 }}
            />
          </Card>
        </Col>
      </Row>

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
                <Row gutter={[16, 16]}>
                  <Col xs={24} md={12}>
                    <Card title="百度热搜 Top 10" size="small">
                      <TopKeywordList items={dashboard?.baidu?.top_keywords ?? []} />
                    </Card>
                  </Col>
                  <Col xs={24} md={12}>
                    <Card title="Google Trends Top 10" size="small">
                      <TopKeywordList items={dashboard?.google?.top_keywords ?? []} />
                    </Card>
                  </Col>
                </Row>
              ),
            },
            {
              key: 'list',
              label: '历史明细',
              children: (
                <Space direction="vertical" style={{ width: '100%' }} size="middle">
                  <Space wrap>
                    <Select
                      placeholder="来源"
                      value={source}
                      onChange={setSource}
                      allowClear
                      style={{ width: 120 }}
                      options={SOURCES}
                    />
                    <Select
                      placeholder="分类"
                      value={category}
                      onChange={setCategory}
                      allowClear
                      style={{ width: 120 }}
                      options={CATEGORIES}
                    />
                    <Input
                      placeholder="搜索关键词"
                      value={searchText}
                      onChange={(e) => setSearchText(e.target.value)}
                      style={{ width: 200 }}
                      prefix={<SearchOutlined />}
                      allowClear
                    />
                  </Space>
                  {listLoading ? (
                    <Skeleton active />
                  ) : !listData || listData.items.length === 0 ? (
                    <Empty description="暂无搜索热度数据" />
                  ) : (
                    <Table
                      rowKey="id"
                      dataSource={listData.items}
                      columns={listColumns}
                      size="small"
                      pagination={{
                        current: page,
                        pageSize: 20,
                        total: listData.total,
                        onChange: setPage,
                      }}
                    />
                  )}
                </Space>
              ),
            },
            {
              key: 'compare',
              label: '关键词对比',
              children: (
                <Space direction="vertical" style={{ width: '100%' }} size="middle">
                  <Space>
                    <Input
                      placeholder="输入关键词 (如 上证指数)"
                      value={compareKeyword ?? ''}
                      onChange={(e) => setCompareKeyword(e.target.value || null)}
                      style={{ width: 240 }}
                      prefix={<SearchOutlined />}
                      allowClear
                    />
                  </Space>
                  {!compareKeyword ? (
                    <Empty description="请输入关键词以查看对比" />
                  ) : compareLoading ? (
                    <Skeleton active />
                  ) : !compareData || compareData.series.length === 0 ? (
                    <Empty description="暂无该关键词数据" />
                  ) : (
                    <Table
                      rowKey="id"
                      dataSource={compareData.series}
                      columns={compareColumns}
                      size="small"
                      pagination={false}
                    />
                  )}
                </Space>
              ),
            },
          ]}
        />
      </Panel>
    </div>
  );
}

function TopKeywordList({ items }: { items: SearchTrend[] }) {
  if (items.length === 0) {
    return <Empty description="暂无数据" />;
  }
  return (
    <div>
      {items.map((item, idx) => (
        <div
          key={item.id}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            padding: '6px 0',
            borderBottom: idx < items.length - 1 ? '1px solid var(--border-default)' : 'none',
          }}
        >
          <Space>
            <Tag color={item.source === 'baidu' ? 'blue' : 'green'}>#{idx + 1}</Tag>
            <span style={{ fontWeight: 500 }}>{item.keyword}</span>
            {item.category && <Tag color="purple">{item.category}</Tag>}
          </Space>
          <span style={{ fontFamily: 'var(--font-mono)' }}>
            {item.value.toLocaleString()}
          </span>
        </div>
      ))}
    </div>
  );
}