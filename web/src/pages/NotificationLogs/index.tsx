import { useState } from 'react';
import { Table } from 'antd';
import { useQuery } from '@tanstack/react-query';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import SectionHeading from '@/components/SectionHeading';
import FilterToolbar from '@/components/FilterToolbar';
import EmptyState from '@/components/EmptyState';
import { notificationApi } from '@/api/notification';
import StatusTag from '@/components/StatusTag';
import { formatDateTime } from '@/utils/datetime';

export default function NotificationLogs() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const { data, isLoading } = useQuery({
    queryKey: ['notification-logs', page, pageSize],
    queryFn: () =>
      notificationApi.logs(page, pageSize).then((r) => r.data),
  });

  const columns = [
    // #15 Typography — tabular figures for numeric/id columns.
    { title: 'ID', dataIndex: 'id', width: 70, render: (v: number) => <span className="tabular-nums">{v}</span> },
    { title: '用户', dataIndex: 'user_id', width: 120, render: (v?: string) => v || '-' },
    { title: '渠道', dataIndex: 'channel', width: 100, render: (v?: string) => v || '-' },
    {
      title: '目标',
      dataIndex: 'target',
      width: 220,
      ellipsis: true,
      render: (v?: string) => v || '-',
    },
    { title: '配置ID', dataIndex: 'config_id', width: 90, render: (v?: number) => v == null ? '-' : <span className="tabular-nums">{v}</span> },
    {
      title: '报告ID',
      dataIndex: 'report_id',
      render: (v?: number) => (v == null ? '-' : <span className="tabular-nums">{v}</span>),
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
      render: (v?: string) => formatDateTime(v),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (v?: string) => formatDateTime(v),
    },
  ];

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="系统"
        title="通知日志"
        description="查看通知发送历史与状态"
      />

      <SectionHeading title="通知发送日志" />
      <Panel variant="default" padding="md">
        <FilterToolbar total={data?.total ?? 0} />

        <div className="ad-table-scroll">
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
            locale={{
              emptyText: <EmptyState title="暂无通知日志" description="当前没有通知发送记录" />,
            }}
          />
        </div>
      </Panel>
    </PageShell>
  );
}
