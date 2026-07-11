import { useMemo, useState } from 'react';
import {
  Table, Input, Select, DatePicker, Button, Space, Tag, Skeleton, message,
} from 'antd';
import { SearchOutlined, ReloadOutlined, CalendarOutlined, FileTextOutlined } from '@ant-design/icons';
import { type Dayjs } from 'dayjs';
import PageShell from '@/components/PageShell';
import Panel from '@/components/Panel';
import FilterToolbar from '@/components/FilterToolbar';
import EmptyState from '@/components/EmptyState';
import HelpTrigger from '@/components/HelpTrigger';
import PageHeader from '@/components/PageHeader';
import LastUpdated from '@/components/LastUpdated';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import {
  useCninfoReportList,
  useCninfoReportCoverage,
  useCninfoReportDetail,
  useRefreshCninfoReports,
} from '@/api/cninfoReportApi';
import type { CninfoReport, CninfoAdjunctType, CninfoReportDetail } from '@/types/cninfoReport';
import { useDebounce } from '@/hooks/useDebounce';

const ADJUNCT_LABEL: Record<string, string> = {
  annual: '年报',
  semi: '半年报',
  q1: '一季报',
  q3: '三季报',
  other: '其他',
};

const ADJUNCT_COLOR: Record<string, string> = {
  annual: 'purple',
  semi: 'blue',
  q1: 'cyan',
  q3: 'gold',
  other: 'default',
};

const ADJUNCT_OPTIONS = (['annual', 'semi', 'q1', 'q3', 'other'] as CninfoAdjunctType[]).map(
  (v) => ({ label: ADJUNCT_LABEL[v] ?? v, value: v }),
);

const formatDate = (v: string | null | undefined): string => v ?? '-';

const formatBytes = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return '-';
  if (v < 1024) return `${v} B`;
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`;
  return `${(v / (1024 * 1024)).toFixed(1)} MB`;
};

export default function CninfoReportsPage() {
  const [search, setSearch] = useState('');
  const [adjunctType, setAdjunctType] = useState<CninfoAdjunctType | undefined>();
  const [fiscalYear, setFiscalYear] = useState<number | undefined>();
  const [hasText, setHasText] = useState<boolean | undefined>();
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const debouncedSearch = useDebounce(search, 300);

  const listParams = useMemo(
    () => ({
      ts_code: debouncedSearch || undefined,
      fiscal_year: fiscalYear,
      adjunct_type: adjunctType,
      has_text: hasText,
      start_date: dateRange?.[0]?.format('YYYY-MM-DD'),
      end_date: dateRange?.[1]?.format('YYYY-MM-DD'),
      page,
      page_size: pageSize,
    }),
    [debouncedSearch, fiscalYear, adjunctType, hasText, dateRange, page, pageSize],
  );

  const { data, isLoading, refetch, dataUpdatedAt, isFetching } = useCninfoReportList(listParams);
  const { data: coverage } = useCninfoReportCoverage();
  const { data: detail, isLoading: detailLoading } = useCninfoReportDetail(detailId);
  const refreshMutation = useRefreshCninfoReports();

  const handleReset = () => {
    setSearch('');
    setAdjunctType(undefined);
    setFiscalYear(undefined);
    setHasText(undefined);
    setDateRange(null);
    setPage(1);
  };

  const handleOpenDetail = (id: number) => {
    setDetailId(id);
    setDetailOpen(true);
  };

  const handleCloseDetail = () => {
    setDetailOpen(false);
    setDetailId(null);
  };

  const handleRefresh = async () => {
    try {
      const res = await refreshMutation.mutateAsync();
      message.success(`刷新成功：写入 ${res.records} 条记录`);
      refetch();
    } catch (err: any) {
      const detail = err?.response?.data?.detail ?? '刷新失败';
      message.error(detail);
    }
  };

  const columns = [
    {
      title: '证券代码',
      dataIndex: 'ts_code',
      width: 140,
      render: (v: string, record: CninfoReport) => (
        <Button
          type="link"
          size="small"
          className="tabular-nums"
          onClick={() => handleOpenDetail(record.id)}
        >
          <InstrumentCodeTag code={v} name={record.stock_name} />
        </Button>
      ),
    },
    {
      title: '公告标题',
      dataIndex: 'announcement_title',
      ellipsis: true,
    },
    {
      title: '报告类型',
      dataIndex: 'adjunct_type',
      width: 90,
      render: (v: string) => (
        <Tag color={ADJUNCT_COLOR[v] ?? 'default'}>{ADJUNCT_LABEL[v] ?? v}</Tag>
      ),
    },
    {
      title: '财年',
      dataIndex: 'fiscal_year',
      width: 80,
      render: (v: number | null) =>
        v !== null && v !== undefined ? (
          <span className="tabular-nums">{v}</span>
        ) : (
          '-'
        ),
    },
    {
      title: '披露时间',
      dataIndex: 'announcement_time',
      width: 160,
      render: formatDate,
    },
    {
      title: '文本提取',
      dataIndex: 'extraction_status',
      width: 100,
      render: (v: string, record: CninfoReport) => {
        const color =
          v === 'extracted' ? 'green' : v === 'failed' ? 'red' : v === 'downloaded' ? 'blue' : 'default';
        return (
          <Space size={4} direction="vertical">
            <Tag color={color}>{v}</Tag>
            {record.extracted_at ? (
              <span className="last-updated">{formatBytes(record.file_size)}</span>
            ) : null}
          </Space>
        );
      },
    },
  ];

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const yearOptions = (coverage?.fiscal_year_breakdown
    ? Object.keys(coverage.fiscal_year_breakdown).map(Number).sort((a, b) => b - a)
    : []);

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="研究"
        title="巨潮定期报告"
        description="沪深 300 + 中证 500 成分股 (B 档) 定期报告库"
        extra={
          <Space size="middle">
            <LastUpdated at={dataUpdatedAt} loading={isFetching && !data} />
            <HelpTrigger tooltip="AI 解读巨潮报告数据" />
            <Button
              icon={<ReloadOutlined />}
              loading={refreshMutation.isPending}
              onClick={handleRefresh}
            >
              刷新
            </Button>
          </Space>
        }
      />

      {coverage ? (
        <Panel variant="default" title="覆盖度">
          <div className="ad-metric-strip">
            <div className="ad-metric-item">
              <div className="ad-metric-item__label">报告总数</div>
              <div className="ad-metric-item__value">{coverage.total_reports}</div>
            </div>
            <div className="ad-metric-item">
              <div className="ad-metric-item__label">覆盖股票</div>
              <div className="ad-metric-item__value">{coverage.stocks_covered}</div>
            </div>
            <div className="ad-metric-item">
              <div className="ad-metric-item__label">已提取文本</div>
              <div className="ad-metric-item__value">{coverage.stocks_with_text}</div>
            </div>
          </div>
        </Panel>
      ) : null}

      <FilterToolbar total={total}>
        <Input
          placeholder="搜索 ts_code (如 600519.SH)"
          allowClear
          prefix={<SearchOutlined />}
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          className="ad-w-full"
        />
        <Select
          placeholder="报告类型"
          allowClear
          className="ad-w-full"
          value={adjunctType}
          onChange={(v) => {
            setAdjunctType(v);
            setPage(1);
          }}
          options={ADJUNCT_OPTIONS}
        />
        <Select
          placeholder="财年"
          allowClear
          className="ad-w-full"
          value={fiscalYear}
          onChange={(v) => {
            setFiscalYear(v);
            setPage(1);
          }}
          options={yearOptions.map((y) => ({ label: String(y), value: y }))}
        />
        <Select
          placeholder="文本提取"
          allowClear
          className="ad-w-full"
          value={hasText}
          onChange={(v) => {
            setHasText(v);
            setPage(1);
          }}
          options={[
            { label: '已提取', value: true },
            { label: '未提取', value: false },
          ]}
        />
        <DatePicker.RangePicker
          value={dateRange as [Dayjs, Dayjs] | null}
          onChange={(v) => {
            setDateRange(v);
            setPage(1);
          }}
          placeholder={['披露 起', '披露 止']}
          suffixIcon={<CalendarOutlined />}
        />
        <Button onClick={handleReset}>重置</Button>
      </FilterToolbar>

      <Panel variant="default" padding="none">
        {isLoading ? (
          <Skeleton active paragraph={{ rows: 10 }} />
        ) : items.length === 0 ? (
          <EmptyState
            icon={<FileTextOutlined />}
            title="暂无符合条件的巨潮报告"
            description="尝试调整筛选条件或刷新数据"
          />
        ) : (
          <div className="ad-table-scroll ad-table-sticky">
            <Table
              dataSource={items}
              columns={columns}
              rowKey="id"
              scroll={{ x: 'max-content' }}
              pagination={{
                current: page,
                pageSize,
                total,
                onChange: setPage,
                showSizeChanger: false,
                showTotal: (t) => `共 ${t} 条`,
              }}
              onRow={(record) => ({
                onClick: () => handleOpenDetail(record.id),
              })}
            />
          </div>
        )}
      </Panel>

      <CninfoReportDetailDrawer
        open={detailOpen}
        loading={detailLoading}
        report={detail ?? null}
        onClose={handleCloseDetail}
      />
    </PageShell>
  );
}

function CninfoReportDetailDrawer({
  open,
  loading,
  report,
  onClose,
}: {
  open: boolean;
  loading: boolean;
  report: CninfoReportDetail | null;
  onClose: () => void;
}) {
  // Lightweight detail drawer implemented as a modal — keeps the page
  // bundle small and avoids pulling in antd's Drawer for one view.
  if (!open) return null;

  return (
    <div
      className="ad-detail-drawer-overlay"
      onClick={onClose}
    >
      <div
        className="ad-detail-drawer"
        onClick={(e) => e.stopPropagation()}
      >
        {loading || !report ? (
          <Skeleton active paragraph={{ rows: 8 }} />
        ) : (
          <>
            <h3>{report.announcement_title}</h3>
            <Space size="small" wrap>
              <Tag color={ADJUNCT_COLOR[report.adjunct_type] ?? 'default'}>
                {ADJUNCT_LABEL[report.adjunct_type] ?? report.adjunct_type}
              </Tag>
              <InstrumentCodeTag code={report.ts_code} name={report.stock_name} />
              <span>{formatDate(report.announcement_time)}</span>
            </Space>

            <Panel variant="minimal" title="元数据" className="ad-mt-4">
              <pre className="font-mono ad-pre-wrap">
{JSON.stringify(
                  {
                    announcement_id: report.announcement_id,
                    adjunct_url: report.adjunct_url,
                    file_path: report.file_path,
                    file_size: report.file_size,
                    fiscal_year: report.fiscal_year,
                    fiscal_quarter: report.fiscal_quarter,
                    extraction_status: report.extraction_status,
                    extracted_at: report.extracted_at,
                    source: report.source,
                  },
                  null,
                  2,
                )}
              </pre>
            </Panel>

            {report.extracted_text_preview ? (
              <Panel variant="minimal" title="文本预览 (前 500 字)" className="ad-mt-4">
                <div className="ad-pre-wrap">
                  {report.extracted_text_preview}
                </div>
              </Panel>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
