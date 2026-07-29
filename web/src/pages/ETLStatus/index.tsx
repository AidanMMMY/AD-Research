import { useState } from 'react';
import { Table, Select, Input, Pagination } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { etlApi } from '@/api/etl';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import SectionHeading from '@/components/SectionHeading';
import FilterToolbar from '@/components/FilterToolbar';
import EmptyState from '@/components/EmptyState';
import LoadingBlock from '@/components/LoadingBlock';
import './styles.css';
import StatusTag from '@/components/StatusTag';
import { useDebounce } from '@/hooks/useDebounce';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { formatDateTime } from '@/utils/datetime';

const STATUS_OPTIONS = [
  { label: '全部', value: '' },
  { label: '成功', value: 'success' },
  { label: '运行中', value: 'running' },
  { label: '失败', value: 'failed' },
  { label: '等待中', value: 'pending' },
  { label: '跳过', value: 'skipped' },
];

export default function ETLStatus() {
  const isMobile = useIsMobile();
  const [status, setStatus] = useState('');
  const [jobName, setJobName] = useState('');
  // Mobile row-list paginates client-side (desktop table paginates
  // internally over the same ≤50-item payload).
  const [etlPage, setEtlPage] = useState(1);
  // Apple Design #1 Response — debounce the query so each keystroke doesn't
  // fire a request; only the settled value (after 300 ms of idle) hits the
  // network, keeping the input feel instant while saving the backend.
  const debouncedJobName = useDebounce(jobName, 300);
  const { data, isLoading } = useQuery({
    queryKey: ['etl-status', status, debouncedJobName],
    queryFn: () =>
      etlApi
        .status({
          status: status || undefined,
          job_name: debouncedJobName || undefined,
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
      render: (v?: string) => formatDateTime(v),
    },
    {
      title: '结束时间',
      dataIndex: 'end_time',
      render: (v?: string) => formatDateTime(v),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      render: (v?: string) => formatDateTime(v),
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
        <FilterToolbar className="etl-status__filters">
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

        {isMobile ? (
          /* Mobile: hairline row-list (read-only log rows, matching
             desktop's non-clickable rows). */
          isLoading ? (
            <LoadingBlock size="md" />
          ) : (data?.items || []).length === 0 ? (
            <EmptyState title="暂无 ETL 日志" description="当前没有符合条件的管道运行记录" />
          ) : (
            <>
              <div className="row-list">
                {(data?.items || [])
                  .slice((etlPage - 1) * 20, etlPage * 20)
                  .map((r: any) => (
                    <div key={r.id} className="hairline-row etl-mrow">
                      <div className="etl-mrow__main">
                        <div className="etl-mrow__title">{r.job_name}</div>
                        <div className="etl-mrow__meta">
                          <StatusTag status={r.status} />
                          <span>{formatDateTime(r.start_time)}</span>
                          {r.error_msg && (
                            <span className="etl-mrow__error" title={r.error_msg}>
                              {r.error_msg}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="etl-mrow__side tnum">
                        {r.records_count == null ? '-' : r.records_count.toLocaleString()}
                      </div>
                    </div>
                  ))}
              </div>
              <Pagination
                current={etlPage}
                pageSize={20}
                total={data?.items?.length ?? 0}
                onChange={setEtlPage}
                size="small"
                showSizeChanger={false}
                className="etl-status__pagination"
              />
            </>
          )
        ) : (
        <Table
          dataSource={data?.items || []}
          columns={columns}
          rowKey="id"
          loading={isLoading}
          pagination={{ pageSize: 20 }}
          scroll={{ x: 'max-content' }}
        />
        )}
      </Panel>
    </PageShell>
  );
}
