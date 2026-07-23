import './styles.css';
import { Alert, Badge, Button, Spin, Statistic, Table, Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { newsApi } from '@/api/news';
import type { NewsHealthResponse, NewsSourceHealth, NewsWorkerStatus } from '@/types/news';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import Panel from '@/components/Panel';
import DataFreshnessHint from '@/components/DataFreshnessHint';
import StatCard from '@/components/StatCard';
import ThemeTag, { type ThemeTagVariant } from '@/components/ThemeTag';
import EmptyState from '@/components/EmptyState';
import { formatDateTime, toLocal } from '@/utils/datetime';

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

/** HealthTone → ThemeTag variant (green/yellow/red → success/warning/error). */
const TONE_VARIANT: Record<HealthTone, ThemeTagVariant> = {
  green: 'success',
  yellow: 'warning',
  red: 'error',
};

/**
 * "x 分钟后 / x 小时后 / x 天后" countdown for a scheduler job's next
 * run time. Past timestamps (clock skew / paused job) read as 已过期.
 */
function formatCountdown(iso: string | null): string {
  if (!iso) return '—';
  const t = toLocal(iso);
  if (!t.isValid()) return '—';
  const diffMin = Math.round((t.valueOf() - Date.now()) / 60000);
  if (diffMin < 0) return '已过期';
  if (diffMin < 1) return '即将运行';
  if (diffMin < 60) return `${diffMin} 分钟后`;
  const h = Math.floor(diffMin / 60);
  if (h < 24) return `${h} 小时后`;
  return `${Math.floor(h / 24)} 天后`;
}

function fmtTime(iso: string | null): string {
  if (!iso) return '—';
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

function workerStatusProps(status: string): { variant: ThemeTagVariant; label: string } {
  const s = status.toLowerCase();
  if (s === 'success') return { variant: 'success', label: '正常' };
  if (s === 'failed') return { variant: 'error', label: '失败' };
  if (s === 'never_run') return { variant: 'neutral', label: '未运行' };
  return { variant: 'warning', label: status || '未知' };
}

export default function NewsHealth() {
  const { data, isLoading, refetch, isRefetching, dataUpdatedAt } = useQuery<NewsHealthResponse>({
    queryKey: ['news-health'],
    queryFn: () => newsApi.health().then((r) => r.data),
    refetchInterval: REFRESH_MS,
  });

  const schedulerRunning = data?.scheduler_running ?? false;
  const jobs = data?.scheduler_jobs ?? [];
  const sources: NewsSourceHealth[] = data?.sources ?? [];
  const workers: NewsWorkerStatus[] = data?.workers ?? [];
  const workerTotal = workers.length;
  const workerHealthy = workers.filter((w) => w.last_status.toLowerCase() === 'success').length;
  const workerUnhealthy = workerTotal - workerHealthy;

  /* Multimodal feedback on polled refresh (Apple: causality cue).
     Track which cells changed so we can briefly highlight them after
     each 30s poll instead of letting values silently swap underneath
     the user. The ref holds the previous render's snapshot keyed by
     source key + column so the comparator stays cheap. */
  const prevSnapshotRef = useRef<Map<string, string>>(new Map());
  const changedSourcesRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    const next = new Map<string, string>();
    const changed = new Set<string>();
    for (const row of sources) {
      const key = row.source;
      const snapshot =
        `${row.total}|${row.last_24h}|${row.last_published_at ?? ''}|${row.last_fetched_at ?? ''}|${row.latest_etl?.status ?? ''}|${row.latest_etl?.records ?? ''}`;
      next.set(key, snapshot);
      const prev = prevSnapshotRef.current.get(key);
      if (prev !== undefined && prev !== snapshot) {
        changed.add(key);
      }
    }
    // New rows that did not exist in the previous snapshot are also
    // surfaced — count as "changed" so the flash draws the eye.
    for (const key of next.keys()) {
      if (!prevSnapshotRef.current.has(key)) changed.add(key);
    }
    changedSourcesRef.current = changed;
    prevSnapshotRef.current = next;
  }, [sources]);
  /** Test helper used by the table cells below to gate the flash class. */
  const isSourceChanged = (source: string): boolean =>
    changedSourcesRef.current.has(source);

  /* Same causality cue for the worker table. */
  const prevWorkerSnapshotRef = useRef<Map<string, string>>(new Map());
  const changedWorkersRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    const next = new Map<string, string>();
    const changed = new Set<string>();
    for (const row of workers) {
      const key = row.name;
      const snapshot = `${row.last_status}|${row.last_run ?? ''}|${row.articles_24h}|${row.last_error ?? ''}`;
      next.set(key, snapshot);
      const prev = prevWorkerSnapshotRef.current.get(key);
      if (prev !== undefined && prev !== snapshot) {
        changed.add(key);
      }
    }
    for (const key of next.keys()) {
      if (!prevWorkerSnapshotRef.current.has(key)) changed.add(key);
    }
    changedWorkersRef.current = changed;
    prevWorkerSnapshotRef.current = next;
  }, [workers]);
  const isWorkerChanged = (name: string): boolean => changedWorkersRef.current.has(name);

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
        return <ThemeTag variant={TONE_VARIANT[color]}>{STATUS_LABEL[color]}</ThemeTag>;
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
        v > 0 ? (
          <ThemeTag variant="accent">{v.toLocaleString()} 条</ThemeTag>
        ) : (
          <ThemeTag>0</ThemeTag>
        ),
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
        const variant: ThemeTagVariant =
          etl.status === 'success'
            ? 'success'
            : etl.status === 'failed'
              ? 'error'
              : 'warning';
        return (
          <div>
            <ThemeTag variant={variant}>{etl.status}</ThemeTag>
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

  const workerColumns: ColumnsType<NewsWorkerStatus> = [
    {
      title: 'Worker',
      key: 'worker',
      width: 220,
      render: (_v, row) => (
        <div>
          <div className="ad-font-medium">{row.label}</div>
          <div className="ad-text-xs ad-text-tertiary">{row.name}</div>
        </div>
      ),
    },
    {
      title: '调度周期',
      dataIndex: 'schedule',
      key: 'schedule',
      width: 140,
    },
    {
      title: '状态',
      key: 'status',
      width: 110,
      render: (_v, row) => {
        const { variant, label } = workerStatusProps(row.last_status);
        return <ThemeTag variant={variant}>{label}</ThemeTag>;
      },
    },
    {
      title: '最近运行',
      key: 'last_run',
      width: 220,
      render: (_v, row) => {
        const v = row.last_run;
        const minutes = ageMinutes(v);
        const base = fmtTime(v);
        if (minutes === null) return <span>{base}</span>;
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
      title: '24h 记录数',
      dataIndex: 'articles_24h',
      key: 'articles_24h',
      width: 120,
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: '最近错误',
      key: 'last_error',
      render: (_v, row) => {
        const v = row.last_error;
        if (!v) return <span>—</span>;
        return (
          <Tooltip title={v}>
            <div className="ad-error-ellipsis">{v}</div>
          </Tooltip>
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

      <div className="ad-flex ad-flex-wrap ad-gap-4 ad-mb-4">
        <div className="news-health-stat">
          <StatCard title="Worker 总数" value={workerTotal} loading={isLoading} />
        </div>
        <div className="news-health-stat">
          <StatCard title="正常" value={workerHealthy} loading={isLoading} />
        </div>
        <div className="news-health-stat">
          <StatCard
            title="异常"
            value={
              <span
                style={
                  workerUnhealthy > 0 ? { color: 'var(--color-error)' } : undefined
                }
              >
                {workerUnhealthy}
              </span>
            }
            loading={isLoading}
          />
        </div>
      </div>

      <Panel title="Scheduler 任务" padding="md" className="ad-mb-4">
        {jobs.length > 0 ? (
          <div className="news-health-jobs">
            {jobs.map((j) => (
              <div key={j.id} className="news-health-jobs__row">
                <span className="ad-text-small">{j.name}</span>
                <Tooltip
                  title={
                    j.next_run_time
                      ? `下次运行 ${formatDateTime(j.next_run_time)}`
                      : undefined
                  }
                >
                  <span className="ad-text-xs ad-text-tertiary">
                    {formatCountdown(j.next_run_time)}
                  </span>
                </Tooltip>
              </div>
            ))}
          </div>
        ) : (
          <span className="ad-text-tertiary">暂无 news_* 任务</span>
        )}
      </Panel>

      {/* AI cleanup observability (M22-3, 2026-07-05).
          Surfaces the silent-degradation case in ContentFetcher:
          rows that Jina fetched but DeepSeek refused to clean.
          The four-statistics strip mirrors the
          /api/v1/news/health `ai_cleanup_24h` block. */}
      <Panel title="AI 清理 (近 24h)" padding="md" className="ad-mb-4">
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
            <div className="ad-flex ad-flex-wrap ad-gap-4 news-health__ai-stats">
              <Statistic
                title="已清理"
                value={data.ai_cleanup_24h.cleaned}
                suffix="条"
                valueStyle={{ color: 'var(--color-success)' }}
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
                  color:
                    data.ai_cleanup_24h.failed > 0
                      ? 'var(--color-error)'
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
                    ? 'var(--color-error)'
                    : 'var(--color-success)',
                }}
              />
            </div>
          </>
        ) : (
          <span className="ad-text-tertiary">尚未抓取任何正文</span>
        )}
      </Panel>

      <Spin spinning={isLoading}>
        <Panel title="数据源健康度" padding="md" className="ad-mb-4">
          <Table
            dataSource={sources}
            columns={columns}
            rowKey="source"
            pagination={false}
            size="middle"
            scroll={{ x: 'max-content' }}
            rowClassName={(row) => {
              const classes: string[] = [];
              if (statusColor(row, schedulerRunning) === 'red') classes.push('news-health-row-red');
              if (isSourceChanged(row.source)) classes.push('news-health-row-changed');
              return classes.join(' ');
            }}
          />
        </Panel>

        <Panel title="Worker 健康度" padding="md">
          {workers.length > 0 ? (
            <Table
              dataSource={workers}
              columns={workerColumns}
              rowKey="name"
              pagination={false}
              size="middle"
              scroll={{ x: 'max-content' }}
              rowClassName={(row) =>
                isWorkerChanged(row.name) ? 'news-health-row-changed' : ''
              }
            />
          ) : (
            <EmptyState
              title="暂无 worker 数据"
              description="等待后端接口返回…"
            />
          )}
        </Panel>
      </Spin>
    </PageShell>
  );
}
