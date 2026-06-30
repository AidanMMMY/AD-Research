import { Badge, Descriptions, Spin, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useQuery } from '@tanstack/react-query';
import { etlApi, type ETLTask } from '@/api/etl';
import Panel from '@/components/Panel';

const { Title, Paragraph } = Typography;

const STATUS_COLOR: Record<string, string> = {
  success: 'green',
  failed: 'red',
  running: 'blue',
  pending: 'gold',
  never_run: 'default',
};

function statusBadge(value: string | null | undefined) {
  const key = (value || 'never_run').toLowerCase();
  return <Tag color={STATUS_COLOR[key] || 'default'}>{key.toUpperCase()}</Tag>;
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
          <div style={{ fontWeight: 500 }}>{row.label}</div>
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{row.name}</div>
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
      render: (v?: number) => (v == null ? '-' : v.toLocaleString()),
    },
    {
      title: '耗时(秒)',
      dataIndex: 'duration_seconds',
      key: 'duration',
      width: 100,
      render: (v?: number) => (v == null ? '-' : v.toFixed(2)),
    },
    {
      title: '错误',
      dataIndex: 'error',
      key: 'error',
      render: (v?: string) =>
        v ? (
          <span style={{ color: 'var(--color-loss)' }}>{v}</span>
        ) : (
          <span style={{ color: 'var(--text-tertiary)' }}>-</span>
        ),
    },
  ];

  return (
    <Spin spinning={isLoading || isRefetching}>
      <Title level={2} style={{ marginTop: 0 }}>
        ETL 运维看板
      </Title>
      <Paragraph type="secondary">
        展示调度任务最近一次执行状态、各市场数据新鲜度。30 秒自动刷新。
      </Paragraph>

      <Panel title="总体健康" padding="md">
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
              <Tag color="green">无</Tag>
            ) : (
              staleMarkets.map((m) => (
                <Tag color="red" key={m}>
                  {m}
                </Tag>
              ))
            )}
          </Descriptions.Item>
        </Descriptions>
      </Panel>

      <div style={{ height: 16 }} />

      <Panel
        title="任务状态"
        padding="md"
        extra={
          <a onClick={() => refetch()} aria-label="refresh">
            刷新
          </a>
        }
      >
        <Table
          rowKey="name"
          size="middle"
          columns={columns}
          dataSource={tasks}
          pagination={{ pageSize: 20, hideOnSinglePage: true }}
          scroll={{ x: 'max-content' }}
        />
      </Panel>
    </Spin>
  );
}
