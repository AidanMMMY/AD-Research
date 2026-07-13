/**
 * ETF 持仓历史（ETFs Holdings History）— AD-Research Phase 1.
 *
 * Route: ``/etfs/:code/holdings-history``
 *
 * Lets analysts browse the quarterly top-10 holdings disclosed by an
 * ETF issuer, see how the basket evolved between any two reporting
 * periods, and watch the cumulative top-10 weight drift over time.
 *
 * Layout (light-clean, no glass effects):
 *   ┌──────────────────────────────────────────────────┐
 *   │ PageHeader  (标的 + 名称 + 简要描述)                │
 *   ├──────────────────────────────────────────────────┤
 *   │ KPI row       (最新期 / 上期 / 累计变化 / 期数)    │
 *   │ Sparkline     (累计前 10 权重走势)                │
 *   ├──────────────────────────────────────────────────┤
 *   │ Timeline +   (左侧日期列)                         │
 *   │ Snapshots     (右侧选中期的快照表格)               │
 *   ├──────────────────────────────────────────────────┤
 *   │ Diff panel    (选择 from → to, 查看新增/减少/      │
 *   │                变化)                              │
 *   └──────────────────────────────────────────────────┘
 *
 * Data sources (see ``web/src/api/etfHoldingsHistory.ts``):
 *   - GET /api/v1/etfs/{code}/holdings/snapshots
 *   - GET /api/v1/etfs/{code}/holdings?date=YYYY-MM-DD
 *   - GET /api/v1/etfs/{code}/holdings/diff?from=…&to=…
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Button,
  DatePicker,
  Input,
  Segmented,
  Skeleton,
  Space,
  Table,
  Tag,
  Tooltip,
  message,
} from 'antd';
import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  DiffOutlined,
  FundOutlined,
  ReloadOutlined,
  SearchOutlined,
  StockOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs, { type Dayjs } from 'dayjs';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import SectionHeading from '@/components/SectionHeading';
import StatCard from '@/components/StatCard';
import EmptyState from '@/components/EmptyState';
import Sparkline from '@/components/Sparkline';
import LoadingBlock from '@/components/LoadingBlock';
import ThemeTag from '@/components/ThemeTag';
import LastUpdated from '@/components/LastUpdated';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import { useInstrumentDetail, useInstrumentList } from '@/hooks/useInstrumentList';
import { etfHoldingsHistoryApi } from '@/api/etfHoldingsHistory';
import { useSettingsStore } from '@/stores/settings';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { NULL_PLACEHOLDER } from '@/utils/format';
import './styles.css';
import type {
  ETFHoldingDiffEntry,
  ETFHoldingItem,
  ETFHoldingSnapshot,
} from '@/types/instrument';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format a weight as a percent string (decimal → %). */
function fmtWeight(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return NULL_PLACEHOLDER;
  return `${(v * 100).toFixed(digits)}%`;
}

/** Compact human-readable number (e.g. 12_345_678 → 1234.57万). */
function fmtShares(v: number | null | undefined): string {
  if (v === null || v === undefined) return NULL_PLACEHOLDER;
  if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(2)} 亿`;
  if (Math.abs(v) >= 1e4) return `${(v / 1e4).toFixed(2)} 万`;
  return v.toFixed(0);
}

/** Status → antd Tag variant + label, used in the diff table. */
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

const EMPTY_ARRAY: never[] = [];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

type ViewMode = 'snapshot' | 'diff';

export default function EtfHoldingsHistoryPage() {
  const { code = '' } = useParams<{ code: string }>();
  const navigate = useNavigate();
  const colorConvention = useSettingsStore((s) => s.colorConvention);

  const instrumentQ = useInstrumentDetail(code);
  const isMobile = useIsMobile();

  // -- Snapshot list -------------------------------------------------------
  const snapshotsQ = useQuery({
    queryKey: ['etf-holdings-snapshots', code],
    queryFn: () => etfHoldingsHistoryApi.listSnapshots(code),
    enabled: !!code,
    staleTime: 5 * 60 * 1000,
  });

  const snapshots: ETFHoldingSnapshot[] = snapshotsQ.data?.items ?? EMPTY_ARRAY;
  const latestDate = snapshots[0]?.holdings_as_of_date ?? null;
  const previousDate = snapshots[1]?.holdings_as_of_date ?? null;

  // -- Selected snapshot (timeline → table) --------------------------------
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  useEffect(() => {
    if (selectedDate === null && latestDate) setSelectedDate(latestDate);
  }, [latestDate, selectedDate]);

  const holdingsQ = useQuery({
    queryKey: ['etf-holdings', code, selectedDate],
    queryFn: () =>
      etfHoldingsHistoryApi.getHoldings(code, selectedDate ? { date: selectedDate } : undefined),
    enabled: !!code && !!selectedDate,
    retry: 1,
  });

  // -- Diff (from / to) ----------------------------------------------------
  const [diffFrom, setDiffFrom] = useState<string | null>(null);
  const [diffTo, setDiffTo] = useState<string | null>(null);
  useEffect(() => {
    if (snapshots.length >= 2 && diffFrom === null && diffTo === null) {
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

  // -- View mode (snapshot vs diff) ----------------------------------------
  const [view, setView] = useState<ViewMode>('snapshot');

  // -- Derived KPIs --------------------------------------------------------
  const totalWeightLatest = useMemo(() => {
    if (!holdingsQ.data?.holdings) return null;
    return holdingsQ.data.holdings.reduce(
      (acc, h) => acc + (h.weight ?? 0),
      0,
    );
  }, [holdingsQ.data]);

  const totalWeightPrev = useMemo(() => {
    if (!previousDate) return null;
    return (
      snapshots.find((s) => s.holdings_as_of_date === previousDate)?.total_weight ?? null
    );
  }, [previousDate, snapshots]);

  const totalWeightDelta = useMemo(() => {
    if (totalWeightLatest === null || totalWeightPrev === null) return null;
    return totalWeightLatest - totalWeightPrev;
  }, [totalWeightLatest, totalWeightPrev]);

  // Sparkline series: cumulative top-10 weight per period, oldest → newest
  const sparklineData = useMemo(() => {
    const series = snapshots
      .map((s) => s.total_weight)
      .filter((w): w is number => typeof w === 'number')
      .reverse();
    return series;
  }, [snapshots]);

  // -- Handlers ------------------------------------------------------------
  const handleRefresh = () => {
    snapshotsQ.refetch();
    holdingsQ.refetch();
    diffQ.refetch();
    message.success('已刷新');
  };

  const handleDiffApply = (from: Dayjs | null, to: Dayjs | null) => {
    if (!from || !to) {
      message.warning('请选择 from / to 两个日期');
      return;
    }
    if (from.isSame(to)) {
      message.warning('from 与 to 不能相同');
      return;
    }
    setDiffFrom(from.format('YYYY-MM-DD'));
    setDiffTo(to.format('YYYY-MM-DD'));
  };

  // -- Columns: snapshot table --------------------------------------------
  const snapshotColumns: ColumnsType<ETFHoldingItem> = useMemo(
    () => [
      {
        title: '#',
        key: 'idx',
        width: 48,
        render: (_v, _r, idx) => <span className="tabular-nums">{idx + 1}</span>,
      },
      {
        title: '代码',
        dataIndex: 'holding_code',
        key: 'holding_code',
        width: 220,
        render: (v: string, row) => (
          <InstrumentCodeTag code={v} name={row.holding_name ?? ''} />
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
        title: '权重',
        dataIndex: 'weight',
        key: 'weight',
        width: 110,
        align: 'right',
        render: (v: number | null) => (
          <span className="tabular-nums ad-text-primary">{fmtWeight(v)}</span>
        ),
      },
      {
        title: '股数',
        dataIndex: 'shares',
        key: 'shares',
        width: 130,
        align: 'right',
        render: (v: number | null) => <span className="tabular-nums">{fmtShares(v)}</span>,
      },
      {
        title: '市值',
        dataIndex: 'market_value',
        key: 'market_value',
        width: 130,
        align: 'right',
        render: (v: number | null) => (
          <span className="tabular-nums ad-text-tertiary">
            {v === null ? NULL_PLACEHOLDER : `${(v / 1e8).toFixed(2)} 亿`}
          </span>
        ),
      },
    ],
    [],
  );

  // -- Columns: diff table -------------------------------------------------
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
        render: (v: string, row) => (
          <InstrumentCodeTag code={v} name={row.holding_name ?? ''} />
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

  // ------------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------------
  const instrument = instrumentQ.data;
  const pageTitle = instrument
    ? `${instrument.name}（${instrument.code}）持仓历史`
    : `ETF 持仓历史 ${code}`;

  // ------------------------------------------------------------------
  // No-code case: render an "ETF picker" instead of the detail view so
  // the sidebar menu can land here directly. The user can search /
  // click an ETF to drill into the per-code detail URL.
  // ------------------------------------------------------------------
  if (!code) {
    return <EtfPickerView onPick={(c) => navigate(`/etfs/${c}/holdings-history`)} />;
  }

  return (
    <PageShell maxWidth="wide">
      {/* Back link + PageHeader */}
      <Button
        type="text"
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate(`/instruments/${code}`)}
        className="ad-mb-3"
      >
        返回标的详情
      </Button>

      <PageHeader
        eyebrow="ETF 投研"
        title={pageTitle}
        description={
          instrument
            ? `${instrument.market ?? ''} · ${instrument.category ?? 'ETF'} · ${
                instrument.underlying_index ?? ''
              }`
            : '查看 ETF 季度披露的前十大持仓变化、累计权重走势与单期明细。'
        }
        extra={
          <Space>
            <LastUpdated at={snapshotsQ.dataUpdatedAt} />
            <Button icon={<ReloadOutlined />} onClick={handleRefresh}>
              刷新
            </Button>
          </Space>
        }
        tutorial={
          <>
            左侧时间线选择披露期，右侧是当期前十大持仓；切换到 <b>对比</b> 模式
            可任意挑两期做新增 / 减少 / 加权变化的 diff。KPI 卡显示最新期 / 上期权重与累计变化。
          </>
        }
      />

      {/* KPI Row */}
      <div className="ehh-kpi-row">
        <StatCard
          title="最新期"
          value={latestDate ?? NULL_PLACEHOLDER}
          icon={<StockOutlined />}
          loading={snapshotsQ.isLoading}
        />
        <StatCard
          title="上期"
          value={previousDate ?? NULL_PLACEHOLDER}
          loading={snapshotsQ.isLoading}
        />
        <StatCard
          title="累计前10权重变化 (本期 vs 上期)"
          value={
            totalWeightDelta === null
              ? NULL_PLACEHOLDER
              : `${totalWeightDelta > 0 ? '+' : ''}${(totalWeightDelta * 100).toFixed(2)}%`
          }
          loading={holdingsQ.isLoading || snapshotsQ.isLoading}
        />
        <StatCard
          title="可用期数"
          value={snapshots.length}
          loading={snapshotsQ.isLoading}
        />
      </div>

      {/* Sparkline — cumulative top-10 weight trend */}
      <Panel
        title="累计前 10 权重走势"
        extra={
          <span className="ad-text-small ad-text-tertiary">
            {sparklineData.length} 个披露期
          </span>
        }
        className="ad-mb-5"
      >
        {snapshotsQ.isLoading ? (
          <div className="ehh-skeleton-full">
            <Skeleton.Input active />
          </div>
        ) : sparklineData.length === 0 ? (
          <EmptyState title="暂无权重走势数据" description="该 ETF 尚未披露任何季度的持仓。" />
        ) : (
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
        )}
      </Panel>

      {/* Mode switch */}
      <div className="ehh-mode-switch">
        <SectionHeading
          title={view === 'snapshot' ? '单期持仓' : '两期对比 (diff)'}
          eyebrow={view === 'snapshot' ? 'Snapshot' : 'Diff'}
        />
        <Segmented
          value={view}
          onChange={(v) => setView(v as ViewMode)}
          options={[
            { label: '单期持仓', value: 'snapshot' },
            { label: '两期对比', value: 'diff' },
          ]}
        />
      </div>

      {/* Body: timeline (left) + content (right) */}
      {view === 'snapshot' ? (
        <div className="ehh-snapshot-layout">
          {/* Timeline */}
          <Panel title="披露期">
            {snapshotsQ.isLoading ? (
              <Skeleton active paragraph={{ rows: 4 }} />
            ) : snapshots.length === 0 ? (
              <EmptyState
                title="尚无披露期"
                description="该 ETF 暂无季度披露数据"
              />
            ) : (
              <ul className="ehh-timeline">
                {snapshots.map((s) => {
                  const isActive = s.holdings_as_of_date === selectedDate;
                  return (
                    <li key={s.holdings_as_of_date}>
                      <button
                        type="button"
                        onClick={() => setSelectedDate(s.holdings_as_of_date)}
                        aria-pressed={isActive}
                        className={`ehh-timeline-btn${isActive ? ' ehh-timeline-btn--active' : ''}`}
                      >
                        <div className="ehh-timeline-btn__row">
                          <span className="tabular-nums">{s.holdings_as_of_date}</span>
                          <Tag>{s.holding_count}</Tag>
                        </div>
                        {s.total_weight !== null && s.total_weight !== undefined && (
                          <div className="ad-text-small ad-text-tertiary ehh-timeline-btn__weight">
                            合计 {fmtWeight(s.total_weight)}
                          </div>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </Panel>

          {/* Selected snapshot table */}
          <Panel
            title={
              selectedDate ? (
                <Space>
                  <span>持仓明细</span>
                  <ThemeTag variant="accent">{selectedDate}</ThemeTag>
                </Space>
              ) : (
                '持仓明细'
              )
            }
            extra={
              holdingsQ.data?.holdings_as_of_date ? (
                <span className="ad-text-small ad-text-tertiary">
                  数据截至 {holdingsQ.data.holdings_as_of_date}
                </span>
              ) : undefined
            }
          >
            {holdingsQ.isLoading ? (
              <LoadingBlock size="md" label="加载持仓中…" />
            ) : !holdingsQ.data || holdingsQ.data.holdings.length === 0 ? (
              <EmptyState
                title="该期暂无持仓数据"
                description="可能是新披露期或数据未拉取"
              />
            ) : (
              <div className="ad-table-scroll">
                <Table
                  size="small"
                  onRow={(row) => ({
                    onClick: () => navigate(`/instruments/${row.holding_code}`),
                    style: { cursor: 'pointer' },
                  })}
                  rowKey={(r) => `${r.holding_code}-${r.holdings_as_of_date ?? ''}`}
                  columns={snapshotColumns}
                  dataSource={holdingsQ.data.holdings}
                  pagination={false}
                  scroll={{ x: 800 }}
                />
              </div>
            )}
          </Panel>
        </div>
      ) : (
        // Diff view
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
                disabledDate={(d) =>
                  diffTo ? d.isAfter(dayjs(diffTo)) : false
                }
              />
              <ArrowRightOutlined className="ad-text-tertiary" />
              <span className="ad-text-small ad-text-tertiary">To</span>
              <DatePicker
                value={diffTo ? dayjs(diffTo) : null}
                onChange={(d) => setDiffTo(d ? d.format('YYYY-MM-DD') : null)}
                format="YYYY-MM-DD"
                placeholder="较晚披露期"
                disabledDate={(d) =>
                  diffFrom ? d.isBefore(dayjs(diffFrom)) : false
                }
              />
              <Button
                type="primary"
                onClick={() =>
                  handleDiffApply(
                    diffFrom ? dayjs(diffFrom) : null,
                    diffTo ? dayjs(diffTo) : null,
                  )
                }
              >
                应用
              </Button>
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
                  onRow={(row) => ({
                    onClick: () => navigate(`/instruments/${row.holding_code}`),
                    style: { cursor: 'pointer' },
                  })}
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
      )}
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// EtfPickerView — minimal entry point used when the route is hit without a
// `:code` param (e.g. from the sidebar menu). It lists ETFs with simple
// search and navigates to the per-code detail URL on click.
// ---------------------------------------------------------------------------
function EtfPickerView({ onPick }: { onPick: (code: string) => void }) {
  const [search, setSearch] = useState('');
  const listQ = useInstrumentList({
    instrument_type: 'ETF',
    search: search || undefined,
    page: 1,
    page_size: 50,
  });

  const items = listQ.data?.items ?? EMPTY_ARRAY;

  const columns: ColumnsType<{ code: string; name: string; name_zh?: string | null; market?: string; category?: string }> = [
    {
      title: '代码',
      dataIndex: 'code',
      key: 'code',
      width: 140,
      render: (v: string, row) => <InstrumentCodeTag code={v} name={row.name} name_zh={row.name_zh} />,
    },
    {
      title: '市场',
      dataIndex: 'market',
      key: 'market',
      width: 90,
      render: (v: string | undefined) => v ?? <span className="ad-text-tertiary">{NULL_PLACEHOLDER}</span>,
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 140,
      render: (v: string | undefined) => v ?? <span className="ad-text-tertiary">{NULL_PLACEHOLDER}</span>,
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_v, row) => (
        <Button
          type="link"
          icon={<ArrowRightOutlined />}
          onClick={() => onPick(row.code)}
        >
          查看持仓
        </Button>
      ),
    },
  ];

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="ETF 投研"
        title="ETF 持仓历史"
        description="选择一只 ETF，查看其季度披露的前十大持仓变化、累计权重走势与单期 diff。"
        tutorial={
          <>
            从下表挑选一只 ETF 进入持仓历史详情页；详情页支持时间线浏览 + 两期 diff。
          </>
        }
      />
      <Panel
        title={
          <Space>
            <FundOutlined />
            <span>选择 ETF</span>
          </Space>
        }
        extra={
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="按代码 / 名称搜索"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="ehh-picker-search"
          />
        }
      >
        {listQ.isLoading ? (
          <LoadingBlock size="md" label="加载 ETF 列表中…" />
        ) : items.length === 0 ? (
          <EmptyState
            title="暂无 ETF 数据"
            description={search ? '没有匹配该搜索条件的 ETF' : '数据库内暂未收录 ETF'}
          />
        ) : (
          <Table
            size="small"
            rowKey="code"
            columns={columns}
            dataSource={items}
            scroll={{ x: 'max-content' }}
            pagination={{ pageSize: 50, showSizeChanger: false }}
          />
        )}
      </Panel>
    </PageShell>
  );
}
