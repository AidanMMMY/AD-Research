import './styles.css';
import { Alert, Badge, Button, Spin, Statistic, Table, Tag, Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useQuery } from '@tanstack/react-query';
import { newsApi } from '@/api/news';
import type { NewsSourceHealth } from '@/types/news';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import ContentCard from '@/components/ContentCard';
import DataFreshnessHint from '@/components/DataFreshnessHint';

const REFRESH_MS = 30_000;

type HealthTone = 'green' | 'yellow' | 'red';

/**
 * Decide a colour for the source row.
 *
 *  green : >=5 articles in the last 24h, scheduler running
 *  yellow: 1-4 articles OR scheduler unknown
 *  red   : 0 articles OR scheduler not running OR etl log last failed
 */
function statusColor(row: NewsSourceHealth, schedulerRunning: boolean): HealthTone {
  if (!schedulerRunning) return 'red';
  const etlStatus = row.latest_etl?.status?.toLowerCase();
  if (etlStatus === 'failed') return 'red';
  if (row.last_24h >= 5) return 'green';
  if (row.last_24h >= 1) return 'yellow';
  return 'red';
}

const STATUS_LABEL: Record<HealthTone, string> = {
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

function ageTone(minutes: number | null): string {
  if (minutes === null) return 'var(--text-secondary)';
  if (minutes <= 60) return 'var(--text-secondary)';
  if (minutes <= 6 * 60) return 'var(--color-warning)';
  return 'var(--color-error)';
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
        return (
          <Tooltip title={base}>
            <span className="news-health-age" style={{ color: ageTone(minutes) }}>
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
              <div className="ad-error-ellipsis" title={etl.error_msg}>
                {etl.error_msg}
              </div>
            )}
          </div>
        );
      },
    },
  ];

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="运维"
        title="资讯健康度"
        description="按数据源展示最近 24h 收录量与最新发布时间，并附 scheduler 任务运行状态。自动每 30 秒刷新。"
        extra={
          <div className="ad-flex ad-items-center ad-gap-3">
            <span className="ad-timestamp">
              {dataUpdatedAt
                ? `更新于 ${new Date(dataUpdatedAt).toLocaleTimeString()}`
                : '加载中…'}
            </span>
            <DataFreshnessHint at={dataUpdatedAt} prefix="上次更新" />
            <Button size="small" onClick={() => refetch()} loading={isRefetching}>
              立即刷新
            </Button>
          </div>
        }
      />

      <FilterToolbar
        extra={
          <div className="ad-flex ad-items-center ad-gap-2">
            <Badge
              status={schedulerRunning ? 'success' : 'error'}
              text={
                <span className="ad-font-medium">
                  {schedulerRunning ? 'APScheduler 运行中' : 'APScheduler 未运行'}
                </span>
              }
            />
            <span className="ad-timestamp">
              共注册 {data?.scheduler_total_jobs ?? 0} 个任务，其中 news_* {jobs.length} 个
            </span>
          </div>
        }
      />

      <ContentCard title="Scheduler 任务" className="ad-mb-4">
        {jobs.length > 0 ? (
          <div className="ad-flex ad-flex-wrap ad-gap-2">
            {jobs.map((j) => (
              <Tag key={j.id} color="blue">
                {j.name} · 下次 {j.next_run_time ? new Date(j.next_run_time).toLocaleString() : '—'}
              </Tag>
            ))}
          </div>
        ) : (
          <span className="ad-text-tertiary">暂无 news_* 任务</span>
        )}
      </ContentCard>

      {/* AI cleanup observability (M22-3, 2026-07-05).
          Surfaces the silent-degradation case in ContentFetcher:
          rows that Jina fetched but DeepSeek refused to clean.
          The four-statistics strip mirrors the
          /api/v1/news/health `ai_cleanup_24h` block. */}
      <ContentCard title="AI 清理 (近 24h)" className="ad-mb-4">
        {data?.ai_cleanup_24h ? (
          <>
            {data.ai_cleanup_24h.alert && (
              <Alert
                className="ad-mb-3"
                type="error"
                showIcon
                message="AI 清理失败率过高"
                description={
                  <>
                    近 24h 共有{' '}
                    <strong>
                      {data.ai_cleanup_24h.cleaned_pct.toFixed(1)}%
                    </strong>{' '}
                    的抓取被 DeepSeek 成功清理（阈值{' '}
                    {data.ai_cleanup_24h.alert_threshold_pct.toFixed(1)}%）。
                    请检查 DeepSeek API Key 与配额。
                  </>
                }
              />
            )}
            <div
              className="ad-flex ad-flex-wrap ad-gap-4 news-health__ai-stats"
            >
              <Statistic
                title="已清理"
                value={data.ai_cleanup_24h.cleaned}
                suffix="条"
                valueStyle={{ color: 'var(--color-success, #52c41a)' }}
              />
              <Statistic
                title="跳过 (AI 未配置)"
                value={data.ai_cleanup_24h.skipped}
                suffix="条"
                valueStyle={{ color: 'var(--text-secondary)' }}
              />
              <Statistic
                title="失败"
                value={data.ai_cleanup_24h.failed}
                suffix="条"
                valueStyle={{
                  color: data.ai_cleanup_24h.failed > 0
                    ? 'var(--color-error, #ff4d4f)'
                    : 'var(--text-secondary)',
                }}
              />
              <Statistic
                title="清理成功率"
                value={data.ai_cleanup_24h.cleaned_pct}
                precision={1}
                suffix="%"
                valueStyle={{
                  color: data.ai_cleanup_24h.alert
                    ? 'var(--color-error, #ff4d4f)'
                    : 'var(--color-success, #52c41a)',
                }}
              />
            </div>
          </>
        ) : (
          <span className="ad-text-tertiary">尚未抓取任何正文</span>
        )}
      </ContentCard>

      <Spin spinning={isLoading}>
        <ContentCard title="数据源健康度">
          <Table
            dataSource={sources}
            columns={columns}
            rowKey="source"
            pagination={false}
            size="middle"
            scroll={{ x: 'max-content' }}
            rowClassName={(row) =>
              statusColor(row, schedulerRunning) === 'red' ? 'news-health-row-red' : ''
            }
          />
        </ContentCard>
      </Spin>
    </PageShell>
  );
}
