/**
 * ETF 持仓历史（ETFs Holdings History）— AlloyResearch Phase 1.
 *
 * Route: ``/etfs/:code/holdings-history``（深链保留）
 *
 * 2026-07-27 合并改版：独立「ETF 持仓」菜单已并入标的详情页持仓模块
 * （TypeAwareModules → EtfHoldingsModule），本页降级为深链完整视图。
 * KPI / 权重走势 / 两期 diff 已抽为共享组件 ``components/EtfHoldingsAnalytics``，
 * 去重与格式化工具在 ``utils/etfHoldings.ts``。
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
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button, Segmented, Space, Table, Tag, Tooltip, message } from 'antd';
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import SectionHeading from '@/components/SectionHeading';
import EmptyState from '@/components/EmptyState';
import LoadingBlock from '@/components/LoadingBlock';
import ThemeTag from '@/components/ThemeTag';
import LastUpdated from '@/components/LastUpdated';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import {
  EtfHoldingsDiffView,
  EtfHoldingsKpiRow,
  EtfHoldingsWeightTrend,
} from '@/components/EtfHoldingsAnalytics';
import { useInstrumentDetail } from '@/hooks/useInstrumentList';
import { etfHoldingsHistoryApi } from '@/api/etfHoldingsHistory';
import { NULL_PLACEHOLDER } from '@/utils/format';
import { fmtShares, fmtWeight, isNavigableCode, mergeHoldings } from '@/utils/etfHoldings';
import './styles.css';
import type { ETFHoldingItem, ETFHoldingSnapshot } from '@/types/instrument';

const EMPTY_ARRAY: never[] = [];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

type ViewMode = 'snapshot' | 'diff';

export default function EtfHoldingsHistoryPage() {
  const { code = '' } = useParams<{ code: string }>();
  const navigate = useNavigate();

  const instrumentQ = useInstrumentDetail(code);

  // -- Snapshot list -------------------------------------------------------
  const snapshotsQ = useQuery({
    queryKey: ['etf-holdings-snapshots', code],
    queryFn: () => etfHoldingsHistoryApi.listSnapshots(code),
    enabled: !!code,
    staleTime: 5 * 60 * 1000,
  });

  const snapshots: ETFHoldingSnapshot[] = snapshotsQ.data?.items ?? EMPTY_ARRAY;
  const latestDate = snapshots[0]?.holdings_as_of_date ?? null;

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

  // Holdings deduped by normalised code (bare + suffixed rows collapse).
  const mergedHoldings = useMemo(
    () => mergeHoldings(holdingsQ.data?.holdings ?? []),
    [holdingsQ.data],
  );

  // -- View mode (snapshot vs diff) ----------------------------------------
  const [view, setView] = useState<ViewMode>('snapshot');

  // -- Derived KPI: 最新期前10合计权重（对当前选中期的 holdings 求和）--------
  const totalWeightLatest = useMemo(() => {
    if (!holdingsQ.data?.holdings) return null;
    return holdingsQ.data.holdings.reduce((acc, h) => acc + (h.weight ?? 0), 0);
  }, [holdingsQ.data]);

  // -- Handlers ------------------------------------------------------------
  const handleRefresh = () => {
    snapshotsQ.refetch();
    holdingsQ.refetch();
    message.success('已刷新');
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
        render: (v: string) => (
          <Space size={4}>
            {/* No `name` prop — the adjacent 名称 column already shows it. */}
            <InstrumentCodeTag code={v} />
            {!isNavigableCode(v) && (
              <Tooltip title="代码缺少市场后缀，暂不支持跳转标的详情">
                <ThemeTag variant="neutral">未标准化</ThemeTag>
              </Tooltip>
            )}
          </Space>
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

  // ------------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------------
  const instrument = instrumentQ.data;
  const pageTitle = instrument
    ? `${instrument.name}（${instrument.code}）持仓历史`
    : `ETF 持仓历史 ${code}`;

  // 无 code 的 picker 版已随侧边栏菜单一并移除（2026-07-27）；直接访问
  // /etfs/holdings-history 的兜底走标的列表。
  if (!code) {
    return <Navigate to="/instruments" replace />;
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

      {/* KPI Row — comparison cards only render with ≥2 disclosure periods. */}
      <EtfHoldingsKpiRow
        snapshots={snapshots}
        latestTotalWeight={totalWeightLatest}
        loading={snapshotsQ.isLoading || holdingsQ.isLoading}
      />

      {/* Sparkline — cumulative top-10 weight trend */}
      <Panel
        title="累计前 10 权重走势"
        extra={
          <span className="ad-text-small ad-text-tertiary">
            {snapshots.filter((s) => typeof s.total_weight === 'number').length} 个披露期
          </span>
        }
        className="ad-mb-5"
      >
        <EtfHoldingsWeightTrend snapshots={snapshots} loading={snapshotsQ.isLoading} />
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
      <div key={view} className="ehh-mode-fade">
        {view === 'snapshot' ? (
          <div className="ehh-snapshot-layout">
            {/* Timeline */}
            <Panel title="披露期">
              {snapshotsQ.isLoading ? (
                <LoadingBlock size="md" />
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
                    onRow={(row) =>
                      isNavigableCode(row.holding_code)
                        ? {
                            onClick: () => navigate(`/instruments/${row.holding_code}`),
                            style: { cursor: 'pointer' },
                          }
                        : { title: '代码缺少市场后缀，暂不支持跳转标的详情' }
                    }
                    rowKey="holding_code"
                    columns={snapshotColumns}
                    dataSource={mergedHoldings}
                    pagination={false}
                    scroll={{ x: 800 }}
                  />
                </div>
              )}
            </Panel>
          </div>
        ) : (
          <EtfHoldingsDiffView code={code} snapshots={snapshots} />
        )}
      </div>
    </PageShell>
  );
}
