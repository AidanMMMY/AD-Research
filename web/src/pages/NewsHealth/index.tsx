import { Badge, Button, Spin, Table, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useQuery } from '@tanstack/react-query';
import { newsApi } from '@/api/news';
import type { NewsSourceHealth } from '@/types/news';
import Panel from '@/components/Panel';

const { Title, Paragraph } = Typography;

const REFRESH_MS = 30_000;

/**
 * Decide a colour for the source row.
 *
 *  green : >=5 articles in the last 24h, scheduler running
 *  yellow: 1-4 articles OR scheduler unknown
 *  red   : 0 articles OR scheduler not running OR etl log last failed
 */
function statusColor(row: NewsSourceHealth, schedulerRunning: boolean): 'green' | 'yellow' | 'red' {
  if (!schedulerRunning) return 'red';
  const etlStatus = row.latest_etl?.status?.toLowerCase();
  if (etlStatus === 'failed') return 'red';
  if (row.last_24h >= 5) return 'green';
  if (row.last_24h >= 1) return 'yellow';
  return 'red';
}

const STATUS_LABEL: Record<'green' | 'yellow' | 'red', string> = {
  green: '健康',
  yellow: '偏慢',
  red: '异常',
};

function fmtTime(iso: string | null): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function ageMinutes(iso: string | null): number | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return Math.max(0, Math.round((Date.now() - d.getTime()) / 60000));
}

export default function NewsHealth() {
  const { data, isLoading, refetch, isRefetching, dataUpdatedAt } = useQuery({
    queryKey: ['news-health'],
    queryFn: () => newsApi.health().then((r) => r.data),
    refetchInterval: REFRESH_MS,
  });

  const schedulerRunning = data?.scheduler_running ?? false;
  const jobs = data?.scheduler_jobs ?? [];
  const sources: NewsSourceHealth[] = data?.sources ?? [];

  const columns: ColumnsType<NewsSourceHealth> = [
    {
      title: '数据源',
      dataIndex: 'source',
      key: 'source',
      width: 200,
      render: (v: string, row) => (
        <div>
          <div className="ad-font-medium">{v}</div>
          <div className="ad-text-xs ad-text-tertiary">{row.job_id ?? '—'}</div>
        </div>
      ),
    },
    {
      title: '状态',
      key: 'status',
      width: 110,
      render: (_v, row) => {
        const color = statusColor(row, schedulerRunning);
        return <Tag color={color}>{STATUS_LABEL[color]}</Tag>;
      },
    },
    {
      title: '总数',
      dataIndex: 'total',
      key: 'total',
      width: 90,
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: '最近 24h',
      dataIndex: 'last_24h',
      key: 'last_24h',
      width: 110,
      render: (v: number) =>
        v > 0 ? <Tag color="blue">{v.toLocaleString()} 条</Tag> : <Tag>0</Tag>,
    },
    {
      title: '最新发布',
      dataIndex: 'last_published_at',
      key: 'last_published_at',
      width: 200,
      render: (v: string | null) => {
        const minutes = ageMinutes(v);
        const base = fmtTime(v);
        if (minutes === null) return base;
        const tone =
          minutes <= 60 ? 'var(--text-secondary)' : minutes <= 6 * 60 ? '#d48806' : '#cf1322';
        return (
          <Tooltip title={base}>
            <span style={{ color: tone }}>
              {base} <span className="ad-text-xs">({minutes}m 前)</span>
            </span>
          </Tooltip>
        );
      },
    },
    {
      title: '最新抓取',
      dataIndex: 'last_fetched_at',
      key: 'last_fetched_at',
      width: 200,
      render: (v: string | null) => fmtTime(v),
    },
    {
      title: '最近 ETL',
      key: 'latest_etl',
      render: (_v, row) => {
        const etl = row.latest_etl;
        if (!etl) return <span className="ad-text-tertiary">暂无记录</span>;
        const color =
          etl.status === 'success'
            ? 'green'
            : etl.status === 'failed'
              ? 'red'
              : 'gold';
        return (
          <div>
            <Tag color={color}>{etl.status}</Tag>
            <span className="ad-text-xs ad-ml-2">
              {etl.records != null ? `${etl.records} 条` : '-'}
            </span>
            {etl.error_msg && (
              <div
                className="ad-error-ellipsis"
                title={etl.error_msg}
              >
                {etl.error_msg}
              </div>
            )}
          </div>
        );
      },
    },
  ];

  return (
    <div>
      <div className="ad-page-header">
        <Title level={2} className="ad-page-header__title">
          资讯健康度
        </Title>
        <div className="ad-page-header__actions">
          <span className="ad-timestamp">
            {dataUpdatedAt
              ? `更新于 ${new Date(dataUpdatedAt).toLocaleTimeString()}`
              : '加载中…'}
          </span>
          <Button size="small" onClick={() => refetch()} loading={isRefetching}>
            立即刷新
          </Button>
        </div>
      </div>
      <Paragraph type="secondary" className="ad-mb-5">
        按数据源展示最近 24h 收录量与最新发布时间，并附 scheduler 任务运行状态。
        自动每 30 秒刷新。
      </Paragraph>

      <Panel title="Scheduler 状态" padding="md" className="ad-mb-4">
        <div className="ad-flex ad-flex-wrap ad-gap-4 ad-items-center">
          <Badge
            status={schedulerRunning ? 'success' : 'error'}
            text={
              <span className="ad-font-medium">
                {schedulerRunning ? 'APScheduler 运行中' : 'APScheduler 未运行'}
              </span>
            }
          />
          <span className="ad-timestamp">
            当前进程共注册 {data?.scheduler_total_jobs ?? 0} 个任务，其中 news_* {jobs.length} 个
          </span>
        </div>
        {jobs.length > 0 && (
          <div className="ad-flex ad-flex-wrap ad-gap-2 ad-mt-3">
            {jobs.map((j) => (
              <Tag key={j.id} color="blue">
                {j.name} · 下次 {j.next_run_time ? new Date(j.next_run_time).toLocaleString() : '—'}
              </Tag>
            ))}
          </div>
        )}
      </Panel>

      <Spin spinning={isLoading}>
        <Panel title="数据源健康度" padding="md">
          <Table
            dataSource={sources}
            columns={columns}
            rowKey="source"
            pagination={false}
            size="middle"
            scroll={{ x: 'max-content' }}
            rowClassName={(row) => {
              const color = statusColor(row, schedulerRunning);
              return color === 'red' ? 'news-health-row-red' : '';
            }}
          />
        </Panel>
      </Spin>
    </div>
  );
}