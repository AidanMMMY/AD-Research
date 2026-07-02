import { useMemo, useState } from 'react';
import {
  Table, Input, Select, Button, Space, Tag, Skeleton, message,
} from 'antd';
import { ReloadOutlined, SearchOutlined, FileTextOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import FilterToolbar from '@/components/FilterToolbar';
import EmptyState from '@/components/EmptyState';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import StatCard from '@/components/StatCard';
import LastUpdated from '@/components/LastUpdated';
import {
  useSecFilingList,
  useSecFilingCoverage,
  useRefreshSecFilings,
  useSyncSecTicker,
} from '@/api/secFilings';
import type { SecFiling } from '@/api/secFilings';

const FORM_TYPES = ['10-K', '10-Q', '20-F', '20-F/A', '10-K/A', '10-Q/A'];
const STATUS_COLORS: Record<string, string> = {
  success: 'green',
  failed: 'red',
  pending: 'gold',
};

export default function SECFilingsPage() {
  const [ticker, setTicker] = useState<string | undefined>();
  const [formType, setFormType] = useState<string | undefined>();
  const [searchText, setSearchText] = useState<string>('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const params = useMemo(
    () => ({
      page,
      page_size: pageSize,
      ticker,
      form_type: formType,
      q: searchText || undefined,
    }),
    [page, pageSize, ticker, formType, searchText],
  );

  const { data, isLoading, refetch, dataUpdatedAt } = useSecFilingList(params);
  const { data: coverage } = useSecFilingCoverage();
  const refreshMutation = useRefreshSecFilings();
  const syncMutation = useSyncSecTicker();

  const handleRefresh = async () => {
    try {
      const res = await refreshMutation.mutateAsync(50);
      message.success(`SEC EDGAR 刷新完成: 写入 ${res.records} 条`);
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(`刷新失败: ${detail ?? '未知错误'}`);
    }
  };

  const handleSync = async () => {
    if (!ticker) {
      message.warning('请先填写 Ticker');
      return;
    }
    try {
      const res = await syncMutation.mutateAsync(ticker);
      message.success(`已同步 ${res.ticker}: 新增 ${res.written} 条`);
      refetch();
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(`同步失败: ${detail ?? '未知错误'}`);
    }
  };

  const columns: ColumnsType<SecFiling> = [
    {
      title: 'Ticker',
      dataIndex: 'ticker',
      key: 'ticker',
      width: 100,
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    {
      title: '公司',
      dataIndex: 'company_name',
      key: 'company_name',
      ellipsis: true,
    },
    {
      title: 'Form',
      dataIndex: 'form_type',
      key: 'form_type',
      width: 90,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: 'Filing Date',
      dataIndex: 'filing_date',
      key: 'filing_date',
      width: 120,
    },
    {
      title: 'Report Period',
      dataIndex: 'report_period',
      key: 'report_period',
      width: 120,
    },
    {
      title: '状态',
      dataIndex: 'extraction_status',
      key: 'extraction_status',
      width: 90,
      render: (v: string) => (
        <Tag color={STATUS_COLORS[v] ?? 'default'}>{v}</Tag>
      ),
    },
    {
      title: 'Accession',
      dataIndex: 'accession_number',
      key: 'accession_number',
      width: 220,
      render: (v: string, row: SecFiling) =>
        row.filing_url ? (
          <a href={row.filing_url} target="_blank" rel="noopener noreferrer">
            {v}
          </a>
        ) : (
          v
        ),
    },
  ];

  return (
    <PageShell maxWidth="reading">
      <PageHeader
        title="SEC 公告"
        description="由 SEC EDGAR 公开数据自动采集 S&P 500 成分股的 10-K / 10-Q / 20-F 公告及 GAAP 财务指标。每周六 06:00 UTC 自动刷新。"
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

      <ResponsiveGrid cols={4} gap="md">
        <StatCard
          title="总公告数"
          value={coverage?.total_filings ?? 0}
          icon={<FileTextOutlined />}
        />
        <StatCard
          title="覆盖 Ticker"
          value={coverage?.tracked_tickers ?? 0}
        />
        <div className="detail-kpi-rise">
          <StatCard
            title="XBRL 已提取"
            value={coverage?.extractions_completed ?? 0}
          />
        </div>
        <div className="detail-kpi-accent">
          <StatCard
            title="XBRL 待提取"
            value={coverage?.extractions_pending ?? 0}
          />
        </div>
      </ResponsiveGrid>

      <Panel variant="default" title="公告列表" className="ad-mt-5">
        <FilterToolbar total={data?.total}>
          <Input
            placeholder="Ticker (如 AAPL)"
            value={ticker ?? ''}
            onChange={(e) => setTicker(e.target.value.toUpperCase() || undefined)}
            style={{ width: 120 }}
            allowClear
          />
          <Select
            placeholder="Form 类型"
            value={formType}
            onChange={(v) => setFormType(v)}
            allowClear
            style={{ width: 130 }}
            options={FORM_TYPES.map((f) => ({ value: f, label: f }))}
          />
          <Input
            placeholder="搜索公司名 / Ticker"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 200 }}
            prefix={<SearchOutlined />}
            allowClear
          />
          <Button onClick={handleSync} loading={syncMutation.isPending}>
            同步当前 Ticker
          </Button>
        </FilterToolbar>

        {isLoading ? (
          <Skeleton active />
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            icon={<FileTextOutlined />}
            title="暂无 SEC 公告"
            description="尝试调整筛选条件或同步 Ticker"
          />
        ) : (
          <div className="ad-density-dense ad-table-scroll ad-table-sticky">
            <Table
              rowKey="id"
              dataSource={data.items}
              columns={columns}
              size="small"
              pagination={{
                current: page,
                pageSize,
                total: data.total,
                showSizeChanger: true,
                onChange: (p, ps) => {
                  setPage(p);
                  setPageSize(ps);
                },
              }}
            />
          </div>
        )}
      </Panel>
    </PageShell>
  );
}
