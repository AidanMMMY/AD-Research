import { useState } from 'react';
import { Table, InputNumber } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { notificationApi } from '@/api/notification';
import Panel from '@/components/Panel';
import StatusTag from '@/components/StatusTag';

export default function NotificationLogs() {
  const [limit, setLimit] = useState(50);
  const { data, isLoading } = useQuery({
    queryKey: ['notification-logs', limit],
    queryFn: () => notificationApi.logs(limit).then((r) => r.data),
  });

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
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
      render: (v: string) => <StatusTag status={v} />,
    },
    {
      title: '错误信息',
      dataIndex: 'error_msg',
      render: (v?: string) => v || '-',
    },
    {
      title: '发送时间',
      dataIndex: 'sent_at',
      render: (v?: string) => (v ? new Date(v).toLocaleString() : '-'),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
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

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-3)',
          marginBottom: 'var(--space-4)',
        }}
      >
        <span style={{ color: 'var(--text-secondary)' }}>显示条数：</span>
        <InputNumber
          min={1}
          max={500}
          value={limit}
          onChange={(v) => setLimit(v || 50)}
          style={{ width: 100 }}
        />
      </div>

      <Panel title="通知发送日志" padding="md">
        <Table
          dataSource={data?.items || []}
          columns={columns}
          rowKey="id"
          loading={isLoading}
          pagination={{ pageSize: 20 }}
          scroll={{ x: 'max-content' }}
        />
      </Panel>
    </div>
  );
}
