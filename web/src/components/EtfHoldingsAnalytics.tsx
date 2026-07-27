/**
 * ETF 持仓分析组件集（2026-07-27 独立页 → 详情页合并）。
 *
 * 从 ``pages/EtfHoldingsHistory`` 抽出的三块可复用能力：
 *
 *   - ``EtfHoldingsKpiRow``      — 最新期 / 上期 / 累计前10权重变化 / 可用期数
 *   - ``EtfHoldingsWeightTrend`` — 累计前 10 权重走势 sparkline（仅内容，
 *                                  不带 Panel 外壳，调用方自行包裹）
 *   - ``EtfHoldingsDiffView``    — 两期持仓 diff（自带 from/to 状态与查询）
 *
 * 深链页 ``/etfs/:code/holdings-history`` 与标的详情页的 EtfHoldingsModule
 * 共用这三块，后端端点零改动（见 ``api/etfHoldingsHistory.ts``）。
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { DatePicker, Space, Table, Tooltip } from 'antd';
import { ArrowRightOutlined, DiffOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import Panel from '@/components/Panel';
import StatCard from '@/components/StatCard';
import EmptyState from '@/components/EmptyState';
import Sparkline from '@/components/Sparkline';
import LoadingBlock from '@/components/LoadingBlock';
import ThemeTag from '@/components/ThemeTag';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import { etfHoldingsHistoryApi } from '@/api/etfHoldingsHistory';
import { useSettingsStore } from '@/stores/settings';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { NULL_PLACEHOLDER } from '@/utils/format';
import { fmtShares, fmtWeight, isNavigableCode } from '@/utils/etfHoldings';
import './EtfHoldingsAnalytics.css';
import type { ETFHoldingDiffEntry, ETFHoldingSnapshot } from '@/types/instrument';

const EMPTY_ARRAY: never[] = [];

/** Status → ThemeTag variant + label, used in the diff table. */
const STATUS_META: Record<
  string,
  { label: string; variant: 'success' | 'error' | 'warning' | 'neutral' | 'default' }
> = {
  added: { label: '新增', variant: 'success' },
  removed: { label: '减少', variant: 'error' },
  increased: { label: '加仓', variant: 'success' },
  decreased: { label: '减仓', variant: 'warning' },
  unchanged: { label: '不变', variant: 'neutral' },
};

// ---------------------------------------------------------------------------
// KPI row
// ---------------------------------------------------------------------------

export interface EtfHoldingsKpiRowProps {
  /** Snapshot list, newest first (from /holdings/snapshots). */
  snapshots: ETFHoldingSnapshot[] | undefined;
  /**
   * 最新期前 10 合计权重。调用方决定来源——深链页用当前选中期的
   * holdings 求和，详情页模块直接用 snapshots[0].total_weight。
   */
  latestTotalWeight: number | null;
  loading?: boolean;
}

export function EtfHoldingsKpiRow({
  snapshots,
  latestTotalWeight,
  loading = false,
}: EtfHoldingsKpiRowProps) {
  const list = snapshots ?? EMPTY_ARRAY;
  const latestDate = list[0]?.holdings_as_of_date ?? null;
  const previous = list[1] ?? null;

  const totalWeightDelta = useMemo(() => {
    if (latestTotalWeight === null || previous?.total_weight == null) return null;
    return latestTotalWeight - previous.total_weight;
  }, [latestTotalWeight, previous]);

  return (
    <div className="ehh-kpi-row">
      <StatCard title="最新期" value={latestDate ?? NULL_PLACEHOLDER} loading={loading} />
      {list.length >= 2 && (
        <>
          <StatCard
            title="上期"
            value={previous?.holdings_as_of_date ?? NULL_PLACEHOLDER}
            loading={loading}
          />
          <StatCard
            title="累计前10权重变化 (本期 vs 上期)"
            value={
              totalWeightDelta === null
                ? NULL_PLACEHOLDER
                : `${totalWeightDelta > 0 ? '+' : ''}${(totalWeightDelta * 100).toFixed(2)}%`
            }
            loading={loading}
          />
        </>
      )}
      <StatCard title="可用期数" value={list.length} loading={loading} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Weight trend sparkline (content only — caller supplies the Panel wrapper)
// ---------------------------------------------------------------------------

export interface EtfHoldingsWeightTrendProps {
  snapshots: ETFHoldingSnapshot[] | undefined;
  loading?: boolean;
}

export function EtfHoldingsWeightTrend({ snapshots, loading = false }: EtfHoldingsWeightTrendProps) {
  const isMobile = useIsMobile();

  // Sparkline series: cumulative top-10 weight per period, oldest → newest
  const sparklineData = useMemo(() => {
    return (snapshots ?? EMPTY_ARRAY)
      .map((s) => s.total_weight)
      .filter((w): w is number => typeof w === 'number')
      .reverse();
  }, [snapshots]);

  if (loading) {
    return (
      <div className="ehh-skeleton-full">
        <LoadingBlock size="sm" />
      </div>
    );
  }
  if (sparklineData.length < 2) {
    // A single point would draw a meaningless flat line — compact empty state.
    return (
      <EmptyState
        title="暂无权重走势数据"
        description={
          sparklineData.length === 1
            ? '仅有 1 期披露数据，需 ≥2 期才能绘制走势。'
            : '该 ETF 尚未披露任何季度的持仓。'
        }
      />
    );
  }
  return (
    <div className="ehh-sparkline-row">
      <div className="ehh-sparkline-chart">
        <Sparkline data={sparklineData} width="100%" height={isMobile ? 32 : 48} />
      </div>
      <div className="ehh-sparkline-stats">
        <span className="ad-text-small ad-text-tertiary">最近一期</span>
        <span className="tabular-nums ad-text-primary">
          {fmtWeight(sparklineData[sparklineData.length - 1])}
        </span>
        <span className="ad-text-small ad-text-tertiary">
          最早一期 {fmtWeight(sparklineData[0])}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Diff view (from → to)
// ---------------------------------------------------------------------------

export interface EtfHoldingsDiffViewProps {
  code: string;
  /** Snapshot list (newest first) — used to seed the default from/to. */
  snapshots: ETFHoldingSnapshot[] | undefined;
}

export function EtfHoldingsDiffView({ code, snapshots }: EtfHoldingsDiffViewProps) {
  const navigate = useNavigate();
  const colorConvention = useSettingsStore((s) => s.colorConvention);

  const [diffFrom, setDiffFrom] = useState<string | null>(null);
  const [diffTo, setDiffTo] = useState<string | null>(null);
  useEffect(() => {
    if (snapshots && snapshots.length >= 2 && diffFrom === null && diffTo === null) {
      setDiffFrom(snapshots[1].holdings_as_of_date);
      setDiffTo(snapshots[0].holdings_as_of_date);
    }
  }, [snapshots, diffFrom, diffTo]);

  const diffQ = useQuery({
    queryKey: ['etf-holdings-diff', code, diffFrom, diffTo],
    queryFn: () =>
      etfHoldingsHistoryApi.diffHoldings(code, { from: diffFrom!, to: diffTo! }),
    enabled: !!code && !!diffFrom && !!diffTo && diffFrom !== diffTo,
    retry: 1,
  });

  const diffColumns: ColumnsType<ETFHoldingDiffEntry> = useMemo(
    () => [
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 80,
        render: (v: string) => {
          const meta = STATUS_META[v] ?? { label: v, variant: 'default' as const };
          return <ThemeTag variant={meta.variant}>{meta.label}</ThemeTag>;
        },
      },
      {
        title: '代码',
        dataIndex: 'holding_code',
        key: 'holding_code',
        width: 220,
        render: (v: string) => (
          // No `name` prop — the adjacent 名称 column already shows it.
          <InstrumentCodeTag code={v} />
        ),
      },
      {
        title: '名称',
        dataIndex: 'holding_name',
        key: 'holding_name',
        ellipsis: true,
        render: (v: string | null) => v ?? <span className="ad-text-tertiary">{NULL_PLACEHOLDER}</span>,
      },
      {
        title: '上期权重',
        dataIndex: 'from_weight',
        key: 'from_weight',
        width: 110,
        align: 'right',
        render: (v: number | null) => (
          <span className="tabular-nums ad-text-tertiary">{fmtWeight(v)}</span>
        ),
      },
      {
        title: '本期权重',
        dataIndex: 'to_weight',
        key: 'to_weight',
        width: 110,
        align: 'right',
        render: (v: number | null) => (
          <span className="tabular-nums">{fmtWeight(v)}</span>
        ),
      },
      {
        title: '权重变化',
        dataIndex: 'weight_change',
        key: 'weight_change',
        width: 120,
        align: 'right',
        render: (v: number | null) => {
          if (v === null) return <span className="ad-text-tertiary">{NULL_PLACEHOLDER}</span>;
          const riseClass =
            v > 0.00005
              ? colorConvention === 'us'
                ? 'theme-tag--fall'
                : 'theme-tag--rise'
              : v < -0.00005
              ? colorConvention === 'us'
                ? 'theme-tag--rise'
                : 'theme-tag--fall'
              : 'theme-tag--neutral';
          const sign = v > 0 ? '+' : '';
          return (
            <span className={`tabular-nums ${riseClass.replace('theme-tag--', 'ad-color-')}`}>
              {sign}
              {(v * 100).toFixed(2)}%
            </span>
          );
        },
      },
      {
        title: '股数变化',
        dataIndex: 'shares_change',
        key: 'shares_change',
        width: 130,
        align: 'right',
        render: (v: number | null) => (
          <span className="tabular-nums">
            {v === null ? NULL_PLACEHOLDER : `${v > 0 ? '+' : ''}${fmtShares(v)}`}
          </span>
        ),
      },
    ],
    [colorConvention],
  );

  return (
    <div className="ehh-diff-layout">
      <Panel
        title={
          <Space>
            <DiffOutlined />
            <span>选择对比期</span>
          </Space>
        }
      >
        <Space size="middle" wrap>
          <span className="ad-text-small ad-text-tertiary">From</span>
          <DatePicker
            value={diffFrom ? dayjs(diffFrom) : null}
            onChange={(d) => setDiffFrom(d ? d.format('YYYY-MM-DD') : null)}
            format="YYYY-MM-DD"
            placeholder="较早披露期"
            disabledDate={(d) => (diffTo ? d.isAfter(dayjs(diffTo)) : false)}
          />
          <ArrowRightOutlined className="ad-text-tertiary" />
          <span className="ad-text-small ad-text-tertiary">To</span>
          <DatePicker
            value={diffTo ? dayjs(diffTo) : null}
            onChange={(d) => setDiffTo(d ? d.format('YYYY-MM-DD') : null)}
            format="YYYY-MM-DD"
            placeholder="较晚披露期"
            disabledDate={(d) => (diffFrom ? d.isBefore(dayjs(diffFrom)) : false)}
          />
        </Space>
      </Panel>

      <Panel
        title={
          <Space>
            <span>对比结果</span>
            {diffQ.data && (
              <ThemeTag variant="accent">
                {diffQ.data.from_date} → {diffQ.data.to_date}
              </ThemeTag>
            )}
          </Space>
        }
        extra={
          diffQ.data ? (
            <Space>
              <Tooltip title="新增的持仓">
                <ThemeTag variant="success">+{diffQ.data.added_count} 新增</ThemeTag>
              </Tooltip>
              <Tooltip title="被剔除的持仓">
                <ThemeTag variant="error">-{diffQ.data.removed_count} 减少</ThemeTag>
              </Tooltip>
              <Tooltip title="合计权重差 (to_total − from_total)">
                <ThemeTag variant="accent">
                  权重{' '}
                  {diffQ.data.total_weight_change === null
                    ? NULL_PLACEHOLDER
                    : `${diffQ.data.total_weight_change > 0 ? '+' : ''}${(
                        diffQ.data.total_weight_change * 100
                      ).toFixed(2)}%`}
                </ThemeTag>
              </Tooltip>
            </Space>
          ) : undefined
        }
      >
        {diffQ.isLoading ? (
          <LoadingBlock size="md" label="计算 diff 中…" />
        ) : !diffQ.data || diffQ.data.entries.length === 0 ? (
          <EmptyState
            title="无 diff 数据"
            description="请选择两个不同的披露期进行对比"
          />
        ) : (
          <div className="ad-table-scroll">
            <Table
              size="small"
              onRow={(row) =>
                isNavigableCode(row.holding_code)
                  ? {
                      onClick: () => navigate(`/instruments/${row.holding_code}`),
                      style: { cursor: 'pointer' },
                    }
                  : { title: '代码缺少市场后缀，暂不支持跳转标的详情' }
              }
              rowKey={(r) => r.holding_code}
              columns={diffColumns}
              dataSource={diffQ.data.entries}
              pagination={false}
              scroll={{ x: 900 }}
            />
          </div>
        )}
      </Panel>
    </div>
  );
}
