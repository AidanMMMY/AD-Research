import { useState } from 'react';
import { Table, Button, Space, Modal, Form, Select, message } from 'antd';
import ThemeTag, { ThemeTagVariant } from '@/components/ThemeTag';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import Panel from '@/components/Panel';
import EmptyState from '@/components/EmptyState';
import { EyeOutlined, DownloadOutlined, PlusOutlined, FileTextOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { reportApi, poolApi } from '@/api';
import { useReports } from '@/hooks/useReportStatus';
import type { ReportMetadata } from '@/types/report';

export default function ReportBrowser() {
  const [selectedReport, setSelectedReport] = useState<ReportMetadata | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [form] = Form.useForm();

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

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="研究"
        title="报告浏览"
        description="浏览和下载已生成的投研报告，支持按标的池定制报告"
      />

      <FilterToolbar total={reportList.length}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalOpen(true)}>
          生成报告
        </Button>
      </FilterToolbar>

      {reportList.length === 0 ? (
        <EmptyState
          icon={<FileTextOutlined />}
          title="暂无报告"
          description="点击右上角按钮生成第一份报告"
        />
      ) : (
        <div className="ad-density-dense ad-table-scroll ad-table-sticky">
          <Table
            dataSource={reportList}
            columns={columns}
            rowKey="id"
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
