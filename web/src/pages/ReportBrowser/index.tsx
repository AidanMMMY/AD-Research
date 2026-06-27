import { useState } from 'react';
import { Table, Button, Space, Modal, Form, Select, message } from 'antd';
import GlassCard from '@/components/GlassCard';
import ThemeTag, { ThemeTagVariant } from '@/components/ThemeTag';
import { EyeOutlined, DownloadOutlined, PlusOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { reportApi, poolApi } from '@/api';
import type { ReportMetadata } from '@/types/report';

export default function ReportBrowser() {
  const [selectedReport, setSelectedReport] = useState<ReportMetadata | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [form] = Form.useForm();

  const { data: reports, refetch } = useQuery({
    queryKey: ['reports'],
    queryFn: () => reportApi.list({ limit: 50 }).then((r) => r.data),
  });

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
    };
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

  return (
    <div>
      <h1 style={{ fontSize: 'var(--text-h1-size)', fontWeight: 500, color: 'var(--text-primary)', margin: '0 0 8px', letterSpacing: '-0.03em' }}>报告浏览</h1>
      <p style={{ margin: '0 0 32px', color: 'var(--text-tertiary)', fontSize: 'var(--text-body-size)' }}>浏览和下载已生成的投研报告，支持按标的池定制报告</p>
      <div style={{ marginBottom: 'var(--space-md)', display: 'flex', justifyContent: 'flex-end' }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalOpen(true)}>
          生成报告
        </Button>
      </div>

      <Table dataSource={reports || []} columns={columns} rowKey="id" scroll={{ x: 'max-content' }} />

      {selectedReport?.status === 'done' && (
        <GlassCard title={`报告预览: ${selectedReport.report_type} (${selectedReport.report_date})`} style={{ marginTop: 'var(--space-md)' }}>
          <iframe
            src={reportApi.downloadUrl(selectedReport.id)}
            style={{ width: '100%', height: 600, border: '1px solid var(--border-default)' }}
          />
        </GlassCard>
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
    </div>
  );
}
