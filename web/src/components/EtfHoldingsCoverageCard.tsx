/**
 * "ETF 持仓覆盖率" dashboard card.
 *
 * Backs the operations dashboard's holdings-coverage KPI. Pulls
 *   - the latest snapshot coverage (single-shot, /coverage/latest)
 *   - the per-snapshot history (sparkline, /stats)
 *   - the structural blacklist size (single-shot, /unavailable)
 * in parallel so the number lands as soon as the per-snapshot query
 * returns, then the trend line streams in ~50 ms later.
 *
 * The "合格" badge turns red when any 7/14/30-day SLO threshold is
 * breached — same logic the scheduler job uses to log a WARN, so the
 * UI and the alert log stay in lockstep.
 */
import { useQuery } from '@tanstack/react-query';
import { Skeleton, Tooltip } from 'antd';
import { ExperimentOutlined, WarningOutlined, CheckCircleFilled } from '@ant-design/icons';
import Panel from './Panel';
import Sparkline from './Sparkline';
import { etfHoldingsCoverageApi } from '@/api/etfHoldingsCoverage';

function formatPct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—';
  return `${n.toFixed(1)}%`;
}

function formatDaysAgo(days: number | null | undefined): string {
  if (days == null) return '—';
  if (days < 0) return `${Math.abs(days)} 天后`;
  if (days === 0) return '今天';
  if (days === 1) return '昨天';
  return `${days} 天前`;
}

function severityToColor(severity: string): string {
  if (severity === 'WARN') return 'var(--color-error-bright)';
  if (severity === 'OK') return 'var(--color-success-bright)';
  return 'var(--color-text-secondary)';
}

export default function EtfHoldingsCoverageCard() {
  // Single-shot card payload.
  const latestQuery = useQuery({
    queryKey: ['etf-holdings-coverage-latest'],
    queryFn: () => etfHoldingsCoverageApi.getLatestCoverage(),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  // Trend sparkline — pull up to 8 most recent snapshots.
  const statsQuery = useQuery({
    queryKey: ['etf-holdings-coverage-stats'],
    queryFn: () => etfHoldingsCoverageApi.getStats(),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    select: (data) => data.snapshots.slice(0, 8).reverse(),
  });

  // Blacklist size for the secondary stat.
  const unavailableQuery = useQuery({
    queryKey: ['etf-holdings-unavailable-count'],
    queryFn: () => etfHoldingsCoverageApi.getUnavailable(),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
    select: (data) => data.count,
  });

  const coverage = latestQuery.data?.coverage ?? null;
  const trend = statsQuery.data ?? [];
  const trendPoints = trend.map((s) => s.coverage_pct);
  const unavailableCount = unavailableQuery.data ?? 0;

  const hasAlerts = (coverage?.coverage_alerts?.length ?? 0) > 0;
  const worstAlert = coverage?.coverage_alerts?.[0];

  const isLoading = latestQuery.isPending && !coverage;

  return (
    <Panel
      variant="default"
      padding="md"
      className="dashboard-coverage-card"
      title={
        <span>
          <ExperimentOutlined className="ad-icon-accent" /> ETF 持仓覆盖率
        </span>
      }
      extra={
        hasAlerts && worstAlert ? (
          <Tooltip
            title={
              <span>
                <strong>{(worstAlert.threshold_days)}-天阈值不达标</strong>
                <br />
                实际 {formatPct(worstAlert.actual_coverage_pct)} &lt; 期望{' '}
                {formatPct(worstAlert.min_coverage_pct)}
              </span>
            }
          >
            <span
              className="dashboard-coverage-card__badge dashboard-coverage-card__badge--warn"
              style={{ color: severityToColor(worstAlert.severity) }}
            >
              <WarningOutlined /> {worstAlert.threshold_days}d 未达标
            </span>
          </Tooltip>
        ) : coverage ? (
          <span className="dashboard-coverage-card__badge dashboard-coverage-card__badge--ok">
            <CheckCircleFilled /> 合格
          </span>
        ) : null
      }
    >
      {isLoading ? (
        <Skeleton active paragraph={{ rows: 2 }} />
      ) : !coverage ? (
        <div className="dashboard-coverage-card__empty">
          暂无 ETF 持仓快照 — 请等待季度 ETL 首次跑通
        </div>
      ) : (
        <div className="dashboard-coverage-card__body">
          <div className="dashboard-coverage-card__main">
            <div className="dashboard-coverage-card__pct">
              {formatPct(coverage.coverage_pct)}
            </div>
            <div className="dashboard-coverage-card__meta">
              <span>
                {coverage.etf_count} / {coverage.eligible_etf_count} ETF
              </span>
              <span className="dashboard-coverage-card__divider">·</span>
              <span>{formatDaysAgo(coverage.days_ago)}</span>
            </div>
            <div className="dashboard-coverage-card__date">
              报告期 {coverage.snapshot_date}
            </div>
          </div>
          <div className="dashboard-coverage-card__trend">
            {trendPoints.length >= 2 ? (
              <>
                <Sparkline
                  data={trendPoints}
                  width={120}
                  height={32}
                  color={
                    hasAlerts
                      ? 'var(--color-error-bright)'
                      : 'var(--color-success-bright)'
                  }
                />
                <span className="dashboard-coverage-card__trend-label">
                  近 {trendPoints.length} 季度
                </span>
              </>
            ) : (
              <span className="dashboard-coverage-card__trend-empty">
                等待历史数据
              </span>
            )}
          </div>
        </div>
      )}

      <div className="dashboard-coverage-card__footer">
        <span>黑名单 {unavailableCount} 只</span>
        <span className="dashboard-coverage-card__divider">·</span>
        <span>数据源 {coverage?.sources?.join(' / ') ?? '—'}</span>
        <span className="dashboard-coverage-card__divider">·</span>
        <span>{coverage?.row_count ?? 0} 行</span>
      </div>
    </Panel>
  );
}
