import { useMemo, useState } from 'react';
import {
  Table, Input, Select, Button, Space, Tag, Skeleton, Row, Col, message,
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
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import {
  useSecFilingList,
  useSecFilingCoverage,
  useRefreshSecFilings,
  useSyncSecTicker,
} from '@/api/secFilings';
import type { SecFiling } from '@/api/secFilings';
import { useDebounce } from '@/hooks/useDebounce';

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
  const [statusFilter, setStatusFilter] = useState<'all' | 'pending' | 'success' | 'failed'>('all');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const debouncedTicker = useDebounce(ticker, 300);
  const debouncedSearchText = useDebounce(searchText, 300);

  const params = useMemo(
    () => ({
      page,
      page_size: pageSize,
      ticker: debouncedTicker,
      form_type: formType,
      q: debouncedSearchText || undefined,
    }),
    [page, pageSize, debouncedTicker, formType, debouncedSearchText],
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

  const handleReset = () => {
    setTicker(undefined);
    setFormType(undefined);
    setSearchText('');
    setStatusFilter('all');
    setPage(1);
  };

  // Counts per extraction status across the *currently filtered* page payload.
  // Used by the status chip row so the user can see at a glance how many rows
  // of each kind exist in the current result set.
  const statusCounts = useMemo(() => {
    const counts: Record<'all' | 'pending' | 'success' | 'failed', number> = {
      all: 0,
      pending: 0,
      success: 0,
      failed: 0,
    };
    const items = data?.items ?? [];
    counts.all = items.length;
    for (const item of items) {
      const key = (item.extraction_status ?? '') as 'pending' | 'success' | 'failed';
      if (key in counts) counts[key] += 1;
    }
    return counts;
  }, [data?.items]);

  // Client-side apply of the status filter; the server doesn't expose a
  // status filter param for /sec-filings, so we narrow the result list here.
  const visibleItems = useMemo(() => {
    const items = data?.items ?? [];
    if (statusFilter === 'all') return items;
    return items.filter((it) => it.extraction_status === statusFilter);
  }, [data?.items, statusFilter]);

  const columns: ColumnsType<SecFiling> = [
    {
      title: 'Ticker',
      dataIndex: 'ticker',
      key: 'ticker',
      width: 160,
      render: (v: string, row: SecFiling) => (
        <Tag color="blue">
          <InstrumentCodeTag code={v} name={row.company_name ?? undefined} />
        </Tag>
      ),
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
    <PageShell maxWidth="full">
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
        <div className="ad-mb-3 ad-flex ad-flex-wrap ad-gap-2">
          {(['all', 'pending', 'success', 'failed'] as const).map((key) => {
            const label =
              key === 'all' ? '全部' : key === 'pending' ? '待提取' : key === 'success' ? '已提取' : '失败';
            const active = statusFilter === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => setStatusFilter(key)}
                className={`ad-status-chip ${active ? 'ad-status-chip--active' : ''}`}
                aria-pressed={active}
              >
                <Tag color={STATUS_COLORS[key] ?? 'default'} className="ad-detail-tag">
                  {label}
                </Tag>
                <span className="tabular-nums">{statusCounts[key]}</span>
              </button>
            );
          })}
        </div>

        <FilterToolbar
          total={data?.total}
          extra={
            <Space>
              <Button onClick={handleReset}>重置</Button>
              <Button
                type="primary"
                icon={<ReloadOutlined />}
                onClick={handleSync}
                loading={syncMutation.isPending}
              >
                同步当前 Ticker
              </Button>
            </Space>
          }
        >
          <Row gutter={[12, 8]} style={{ width: '100%' }}>
            <Col xs={24} sm={12} md={8} lg={6}>
              <Input
                placeholder="Ticker (如 AAPL)"
                value={ticker ?? ''}
                onChange={(e) => setTicker(e.target.value.toUpperCase() || undefined)}
                className="ad-w-full"
                allowClear
              />
            </Col>
            <Col xs={24} sm={12} md={8} lg={6}>
              <Select
                placeholder="Form 类型"
                value={formType}
                onChange={(v) => setFormType(v)}
                allowClear
                className="ad-w-full"
                options={FORM_TYPES.map((f) => ({ value: f, label: f }))}
              />
            </Col>
            <Col xs={24} sm={12} md={8} lg={6}>
              <Input
                placeholder="搜索公司名 / Ticker"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                className="ad-w-full"
                prefix={<SearchOutlined />}
                allowClear
              />
            </Col>
          </Row>
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
          <div className="ad-table-scroll ad-table-sticky">
            <Table
              rowKey="id"
              dataSource={visibleItems}
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
