import { useMemo, useState } from 'react';
import { Table, Button, Space, Modal, Form, Select, Input, DatePicker, message } from 'antd';
import ThemeTag, { ThemeTagVariant } from '@/components/ThemeTag';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import Panel from '@/components/Panel';
import EmptyState from '@/components/EmptyState';
import {
  EyeOutlined,
  DownloadOutlined,
  PlusOutlined,
  FileTextOutlined,
  SearchOutlined,
  ReloadOutlined,
  CalendarOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import type { Dayjs } from 'dayjs';
import { reportApi, poolApi } from '@/api';
import { useReports } from '@/hooks/useReportStatus';
import type { ReportMetadata } from '@/types/report';

type ReportStatusFilter = 'all' | ReportMetadata['status'];

const STATUS_FILTERS: { value: ReportStatusFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'pending', label: '待处理' },
  { value: 'running', label: '运行中' },
  { value: 'done', label: '已完成' },
  { value: 'failed', label: '失败' },
];

const TYPE_FILTERS: { value: 'all' | string; label: string }[] = [
  { value: 'all', label: '全部类型' },
  { value: 'pool_weekly', label: '池周报' },
  { value: 'daily', label: '日报' },
];

export default function ReportBrowser() {
  const [selectedReport, setSelectedReport] = useState<ReportMetadata | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [form] = Form.useForm();

  // Filter state — client-side only, no backend changes.
  const [statusFilter, setStatusFilter] = useState<ReportStatusFilter>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [searchText, setSearchText] = useState('');

  // useReports polls every 2s while any in-flight report exists and
  // automatically stops polling once all rows reach a terminal state
  // (handled inside the hook by inspecting the latest data).
  const { data: reports, refetch } = useReports();

  const { data: pools } = useQuery({
    queryKey: ['pools-for-report'],
    queryFn: () => poolApi.list().then((r) => r.data),
  });

  const handleGenerate = async (values: { report_type: string; pool_id: number }) => {
    try {
      await reportApi.generate({
        report_type: values.report_type,
        pool_id: values.pool_id,
        format: 'html',
      });
      message.success('报告生成任务已提交');
      setIsModalOpen(false);
      form.resetFields();
      refetch();
    } catch {
      message.error('提交失败');
    }
  };

  const handleReset = () => {
    setStatusFilter('all');
    setTypeFilter('all');
    setDateRange(null);
    setSearchText('');
  };

  const statusVariants: Record<string, ThemeTagVariant> = {
    pending: 'default',
    running: 'accent',
    done: 'success',
    failed: 'error',
  };

  const columns = [
    { title: '类型', dataIndex: 'report_type', width: 120 },
    { title: '日期', dataIndex: 'report_date', width: 120 },
    { title: '格式', dataIndex: 'format', width: 80 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: string) => <ThemeTag variant={statusVariants[v] || 'default'}>{v}</ThemeTag>,
    },
    {
      title: '操作',
      width: 180,
      render: (_: unknown, record: ReportMetadata) => (
        <Space>
          <Button type="link" icon={<EyeOutlined />} onClick={() => setSelectedReport(record)}>预览</Button>
          {record.status === 'done' && (
            <Button type="link" icon={<DownloadOutlined />} href={reportApi.downloadUrl(record.id)}>下载</Button>
          )}
        </Space>
      ),
    },
  ];

  const reportList = reports || [];

  // Counts per status (unfiltered) drive the chip badges.
  const statusCounts = useMemo(() => {
    const counts: Record<ReportStatusFilter, number> = {
      all: reportList.length,
      pending: 0,
      running: 0,
      done: 0,
      failed: 0,
    };
    for (const r of reportList) {
      if (r.status in counts) {
        counts[r.status as ReportStatusFilter] += 1;
      }
    }
    return counts;
  }, [reportList]);

  // Apply status + type + date + text filters client-side.
  const filteredReports = useMemo(() => {
    const needle = searchText.trim().toLowerCase();
    return reportList.filter((r) => {
      if (statusFilter !== 'all' && r.status !== statusFilter) return false;
      if (typeFilter !== 'all' && r.report_type !== typeFilter) return false;
      if (dateRange && dateRange[0] && dateRange[1]) {
        if (r.report_date < dateRange[0].format('YYYY-MM-DD')) return false;
        if (r.report_date > dateRange[1].format('YYYY-MM-DD')) return false;
      }
      if (needle) {
        const hay = `${r.report_type} ${r.report_date}`.toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
  }, [reportList, statusFilter, typeFilter, dateRange, searchText]);

  const hasActiveFilter =
    statusFilter !== 'all' || typeFilter !== 'all' || !!dateRange || !!searchText.trim();
  const isEmptyFiltered = filteredReports.length === 0;

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="研究"
        title="报告浏览"
        description="浏览和下载已生成的投研报告，支持按标的池定制报告"
      />

      <FilterToolbar
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalOpen(true)}>
            生成报告
          </Button>
        }
      >
        {STATUS_FILTERS.map((s) => (
          <button
            key={s.value}
            type="button"
            onClick={() => setStatusFilter(s.value)}
            className={`ad-status-chip ${statusFilter === s.value ? 'ad-status-chip--active' : ''}`}
            aria-pressed={statusFilter === s.value}
          >
            <span>{s.label}</span>
            <span className="tabular-nums">{statusCounts[s.value]}</span>
          </button>
        ))}
      </FilterToolbar>

      <FilterToolbar total={`共 ${filteredReports.length} 条`}>
        <Select
          className="ad-w-full"
          value={typeFilter}
          onChange={setTypeFilter}
          options={TYPE_FILTERS}
        />
        <DatePicker.RangePicker
          className="ad-w-full"
          value={dateRange as [Dayjs, Dayjs] | null}
          onChange={(v) => setDateRange(v)}
          placeholder={['报告日期 起', '报告日期 止']}
          suffixIcon={<CalendarOutlined />}
        />
        <Input
          className="ad-w-full"
          placeholder="搜索类型或日期"
          allowClear
          prefix={<SearchOutlined />}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
        />
        <Button icon={<ReloadOutlined />} onClick={handleReset} disabled={!hasActiveFilter}>
          重置
        </Button>
      </FilterToolbar>

      {reportList.length === 0 ? (
        <EmptyState
          icon={<FileTextOutlined />}
          title="暂无报告"
          description="点击右上角按钮生成第一份报告"
        />
      ) : isEmptyFiltered ? (
        <EmptyState
          icon={<FileTextOutlined />}
          title="没有符合条件的报告"
          description="尝试调整或重置筛选条件"
          action={
            <Button onClick={handleReset} disabled={!hasActiveFilter}>
              重置筛选
            </Button>
          }
        />
      ) : (
        <div className="ad-table-scroll ad-table-sticky">
          <Table
            dataSource={filteredReports}
            columns={columns}
            rowKey="id"
            scroll={{ x: 'max-content' }}
            pagination={false}
          />
        </div>
      )}

      {selectedReport?.status === 'done' && (
        <Panel title={`报告预览: ${selectedReport.report_type} (${selectedReport.report_date})`} className="ad-mt-5">
          <iframe
            className="ad-preview-frame"
            src={reportApi.downloadUrl(selectedReport.id)}
            title={`报告预览 ${selectedReport.report_type}`}
          />
        </Panel>
      )}

      <Modal
        title="生成报告"
        open={isModalOpen}
        onCancel={() => setIsModalOpen(false)}
        onOk={() => form.submit()}
      >
        <Form form={form} onFinish={handleGenerate} layout="vertical">
          <Form.Item name="report_type" label="报告类型" rules={[{ required: true }]} initialValue="pool_weekly">
            <Select options={[
              { label: '池周报', value: 'pool_weekly' },
              { label: '日报', value: 'daily' },
            ]} />
          </Form.Item>
          <Form.Item name="pool_id" label="标的池" rules={[{ required: true }]}>
            <Select
              options={pools?.map((p) => ({ label: p.name, value: p.id }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}
