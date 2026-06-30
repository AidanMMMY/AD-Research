import { useState } from 'react';
import { Table, InputNumber, Space } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { notificationApi } from '@/api/notification';
import Panel from '@/components/Panel';
import StatusTag from '@/components/StatusTag';

export default function NotificationLogs() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const { data, isLoading } = useQuery({
    queryKey: ['notification-logs', page, pageSize],
    queryFn: () =>
      notificationApi.logs(page, pageSize).then((r) => r.data),
  });

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: '用户', dataIndex: 'user_id', width: 120, render: (v?: string) => v || '-' },
    { title: '渠道', dataIndex: 'channel', width: 100, render: (v?: string) => v || '-' },
    {
      title: '目标',
      dataIndex: 'target',
      width: 220,
      ellipsis: true,
      render: (v?: string) => v || '-',
    },
    { title: '配置ID', dataIndex: 'config_id', width: 90 },
    {
      title: '报告ID',
      dataIndex: 'report_id',
      render: (v?: number) => v ?? '-',
      width: 90,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: string) => <StatusTag status={v} />,
    },
    {
      title: '错误信息',
      dataIndex: 'error',
      width: 200,
      ellipsis: true,
      render: (v?: string) => v || '-',
    },
    {
      title: '发送时间',
      dataIndex: 'sent_at',
      width: 170,
      render: (v?: string) => (v ? new Date(v).toLocaleString() : '-'),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (v?: string) => (v ? new Date(v).toLocaleString() : '-'),
    },
  ];

  return (
    <div>
      <h1
        style={{
          fontSize: 'var(--text-h1-size)',
          fontWeight: 500,
          color: 'var(--text-primary)',
          margin: '0 0 8px',
          letterSpacing: '-0.03em',
        }}
      >
        通知日志
      </h1>
      <p
        style={{
          margin: '0 0 32px',
          color: 'var(--text-tertiary)',
          fontSize: 'var(--text-body-size)',
        }}
      >
        查看通知发送历史与状态
      </p>

      <Space style={{ marginBottom: 'var(--space-4)' }}>
        <span style={{ color: 'var(--text-secondary)' }}>每页条数：</span>
        <InputNumber
          min={1}
          max={200}
          value={pageSize}
          onChange={(v) => {
            setPage(1);
            setPageSize(v || 20);
          }}
          style={{ width: 100 }}
        />
        <span style={{ color: 'var(--text-tertiary)' }}>
          共 {data?.total ?? 0} 条
        </span>
      </Space>

      <Panel title="通知发送日志" padding="md">
        <Table
          dataSource={data?.items || []}
          columns={columns}
          rowKey="id"
          loading={isLoading}
          pagination={{
            current: page,
            pageSize,
            total: data?.total ?? 0,
            showSizeChanger: true,
            pageSizeOptions: ['10', '20', '50', '100'],
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
            },
            showTotal: (total) => `共 ${total} 条`,
          }}
          scroll={{ x: 'max-content' }}
        />
      </Panel>
    </div>
  );
}