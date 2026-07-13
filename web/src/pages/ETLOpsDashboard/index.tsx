import { Badge, Descriptions, Spin, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useQuery } from '@tanstack/react-query';
import { etlApi, type ETLTask } from '@/api/etl';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import SectionHeading from '@/components/SectionHeading';
import ThemeTag from '@/components/ThemeTag';
import EmptyState from '@/components/EmptyState';

function statusBadge(value: string | null | undefined) {
  const key = (value || 'never_run').toLowerCase();
  const variant =
    key === 'success'
      ? 'success'
      : key === 'failed'
      ? 'error'
      : key === 'running'
      ? 'warning'
      : 'neutral';
  const label =
    key === 'success'
      ? 'SUCCESS'
      : key === 'failed'
      ? 'FAILED'
      : key === 'running'
      ? 'RUNNING'
      : key === 'pending'
      ? 'PENDING'
      : 'NEVER RUN';
  return <ThemeTag variant={variant}>{label}</ThemeTag>;
}

function freshnessBadge(value: string | null | undefined, now: Date) {
  if (!value) {
    return <Badge status="error" text="无数据" />;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return <Badge status="default" text={value} />;
  }
  const ageMs = now.getTime() - parsed.getTime();
  const ageDays = ageMs / (1000 * 60 * 60 * 24);
  const isStale = ageDays > 1;
  return (
    <Badge
      status={isStale ? 'error' : 'success'}
      text={`${value} (${ageDays.toFixed(1)}d 前)`}
    />
  );
}

export default function ETLOpsDashboard() {
  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['etl-ops-dashboard'],
    queryFn: () => etlApi.dashboard().then((r) => r.data),
    refetchInterval: 30_000,
  });

  const now = new Date();
  const freshness = data?.data_freshness;
  const tasks: ETLTask[] = data?.tasks ?? [];
  const staleMarkets = data?.stale_markets ?? [];

  const columns: ColumnsType<ETLTask> = [
    {
      title: '任务',
      dataIndex: 'label',
      key: 'label',
      render: (_v, row) => (
        <div>
          <div className="admin-task-label__name">{row.label}</div>
          <div className="admin-task-label__id">{row.name}</div>
        </div>
      ),
    },
    {
      title: '市场',
      dataIndex: 'market',
      key: 'market',
      width: 90,
      render: (v: string) => {
        const label =
          v === 'a_share' ? 'A股' : v === 'us_stock' ? '美股' : v === 'crypto' ? '加密' : v;
        return <Tag>{label}</Tag>;
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (v: string) => statusBadge(v),
    },
    {
      title: '最近运行',
      dataIndex: 'last_run',
      key: 'last_run',
      width: 180,
      render: (v: string | null) => (v ? new Date(v).toLocaleString() : '-'),
    },
    {
      title: '影响行数',
      dataIndex: 'rows_affected',
      key: 'rows_affected',
      width: 110,
      render: (v?: number) =>
        v == null ? (
          '-'
        ) : (
          <span className="tabular-nums">{v.toLocaleString()}</span>
        ),
    },
    {
      title: '耗时(秒)',
      dataIndex: 'duration_seconds',
      key: 'duration',
      width: 100,
      render: (v?: number) =>
        v == null ? '-' : <span className="tabular-nums">{v.toFixed(2)}</span>,
    },
    {
      title: '错误',
      dataIndex: 'error',
      key: 'error',
      render: (v?: string) =>
        v ? (
          <span className="admin-text-error">{v}</span>
        ) : (
          <span className="admin-text-muted">-</span>
        ),
    },
  ];

  return (
    <Spin spinning={isLoading || isRefetching}>
      <PageShell maxWidth="wide">
        {/* Apple Design overrides (WWDC "Designing Fluid Interfaces").
            #1 Response — the refresh link is an <a>, so give it instant
            pointer-down feedback and full keyboard parity with a button. */}
        <style>{`
          .panel-extra-link {
            cursor: pointer;
            user-select: none;
            transition: opacity 0.32s cubic-bezier(0.32, 0.72, 0, 1);
          }
          .panel-extra-link:active { opacity: 0.5; transition: none; }
          .panel-extra-link:focus-visible {
            outline: 2px solid var(--accent);
            outline-offset: 2px;
            border-radius: 2px;
          }
          @media (prefers-reduced-motion: reduce) {
            .panel-extra-link { transition: none; }
          }
        `}</style>
        <PageHeader
          title="ETL 运维看板"
          description="展示调度任务最近一次执行状态、各市场数据新鲜度。30 秒自动刷新。"
          extra={
            <a
              onClick={() => refetch()}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  refetch();
                }
              }}
              role="button"
              tabIndex={0}
              aria-label="refresh"
              className="panel-extra-link"
            >
              刷新
            </a>
          }
        />

        <div className="admin-section">
          <SectionHeading title="总体健康" />
          <Panel variant="default" padding="md">
            {data ? (
              <Descriptions column={2} size="small" bordered>
                <Descriptions.Item label="最近一次运行">
                  {data?.last_run_at
                    ? new Date(data.last_run_at).toLocaleString()
                    : '尚无记录'}
                </Descriptions.Item>
                <Descriptions.Item label="看板生成时间">
                  {data?.generated_at ? new Date(data.generated_at).toLocaleString() : '-'}
                </Descriptions.Item>
                <Descriptions.Item label="A 股数据">
                  {freshnessBadge(freshness?.a_share, now)}
                </Descriptions.Item>
                <Descriptions.Item label="美股数据">
                  {freshnessBadge(freshness?.us_stock, now)}
                </Descriptions.Item>
                <Descriptions.Item label="加密数据">
                  {freshnessBadge(freshness?.crypto, now)}
                </Descriptions.Item>
                <Descriptions.Item label="陈旧市场">
                  {staleMarkets.length === 0 ? (
                    <ThemeTag variant="success">无</ThemeTag>
                  ) : (
                    staleMarkets.map((m) => (
                      <ThemeTag variant="error" key={m}>
                        {m}
                      </ThemeTag>
                    ))
                  )}
                </Descriptions.Item>
              </Descriptions>
            ) : (
              <EmptyState title="加载中..." />
            )}
          </Panel>
        </div>

        <div className="admin-section">
          <SectionHeading title="任务状态" />
          <Panel variant="default" padding="md">
            <Table
              rowKey="name"
              size="middle"
              columns={columns}
              dataSource={tasks}
              pagination={{ pageSize: 20, hideOnSinglePage: true }}
              scroll={{ x: 'max-content' }}
            />
          </Panel>
        </div>
      </PageShell>
    </Spin>
  );
}
