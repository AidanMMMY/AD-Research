import { useState } from 'react';
import { Table, Select, Input } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { etlApi } from '@/api/etl';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import SectionHeading from '@/components/SectionHeading';
import FilterToolbar from '@/components/FilterToolbar';
import './styles.css';
import StatusTag from '@/components/StatusTag';

const STATUS_OPTIONS = [
  { label: '全部', value: '' },
  { label: '成功', value: 'success' },
  { label: '运行中', value: 'running' },
  { label: '失败', value: 'failed' },
  { label: '等待中', value: 'pending' },
];

export default function ETLStatus() {
  const [status, setStatus] = useState('');
  const [jobName, setJobName] = useState('');
  const { data, isLoading } = useQuery({
    queryKey: ['etl-status', status, jobName],
    queryFn: () =>
      etlApi
        .status({
          status: status || undefined,
          job_name: jobName || undefined,
          limit: 50,
        })
        .then((r) => r.data),
  });

  const columns = [
    { title: '任务名称', dataIndex: 'job_name' },
    {
      title: '状态',
      dataIndex: 'status',
      render: (v: string) => <StatusTag status={v} />,
    },
    {
      title: '记录数',
      dataIndex: 'records_count',
      // #15 Typography — tabular figures keep numeric columns aligned.
      render: (v?: number) =>
        v == null ? '-' : <span className="tabular-nums">{v.toLocaleString()}</span>,
    },
    {
      title: '错误信息',
      dataIndex: 'error_msg',
      render: (v?: string) => v || '-',
    },
    {
      title: '开始时间',
      dataIndex: 'start_time',
      render: (v?: string) => (v ? new Date(v).toLocaleString() : '-'),
    },
    {
      title: '结束时间',
      dataIndex: 'end_time',
      render: (v?: string) => (v ? new Date(v).toLocaleString() : '-'),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      render: (v?: string) => (v ? new Date(v).toLocaleString() : '-'),
    },
  ];

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        title="ETL 状态"
        description="查看数据管道运行状态与近期日志"
      />

      <SectionHeading title="近期 ETL 日志" />
      <Panel variant="default" padding="md">
        <FilterToolbar>
          <Input
            placeholder="任务名称"
            value={jobName}
            onChange={(e) => setJobName(e.target.value)}
            className="admin-filter-input"
            allowClear
          />
          <Select
            placeholder="状态"
            value={status}
            onChange={setStatus}
            options={STATUS_OPTIONS}
            className="admin-filter-select"
            allowClear
          />
        </FilterToolbar>

        <Table
          dataSource={data?.items || []}
          columns={columns}
          rowKey="id"
          loading={isLoading}
          pagination={{ pageSize: 20 }}
          scroll={{ x: 'max-content' }}
        />
      </Panel>
    </PageShell>
  );
}
