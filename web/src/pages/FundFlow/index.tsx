import './styles.css';

import { useMemo, useState } from 'react';
import dayjs, { type Dayjs } from 'dayjs';
import {
  Table,
  Tabs,
  Button,
  DatePicker,
  Space,
  Skeleton,
  Collapse,
  Tooltip,
  Tag,
} from 'antd';
import {
  ReloadOutlined,
  RiseOutlined,
  FallOutlined,
  StockOutlined,
  AppstoreOutlined,
  FundOutlined,
  ExperimentOutlined,
  CaretRightOutlined,
  FireOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate } from 'react-router-dom';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import SectionHeading from '@/components/SectionHeading';
import StatCard from '@/components/StatCard';
import Panel from '@/components/Panel';
import EmptyState from '@/components/EmptyState';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import Sparkline from '@/components/Sparkline';
import ExportButton from '@/components/ExportButton';
import ThemeTag from '@/components/ThemeTag';
import ReturnTagPct from '@/components/ReturnTagPct';
import { useChartMotion } from '@/hooks/useChartMotion';
import { clickableRow } from '@/utils/a11y';
import { NULL_PLACEHOLDER, formatNumber } from '@/utils/format';
import {
  useFundFlowMarket,
  useFundFlowIndividual,
  useFundFlowIndividualHistory,
  useFundFlowSector,
  useFundFlowEtf,
  useFundFlowSignals,
  useRefreshFundFlow,
  sortField,
  type IndividualFundFlow,
  type SectorFundFlow,
  type EtfFundFlow,
  type FlowSignal,
  type SectorType,
} from '@/api/fundFlow';

/* =============================================================================
 * Helpers
 * =========================================================================== */

/** Money in 万 / 亿. Returns em-dash for null. Sign is preserved. */
function formatMoney(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return NULL_PLACEHOLDER;
  const abs = Math.abs(v);
  const sign = v < 0 ? '-' : '';
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(digits)} 亿`;
  if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(digits)} 万`;
  return `${sign}${abs.toFixed(digits)}`;
}

/** Percent value with optional sign. */
function formatPct(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return NULL_PLACEHOLDER;
  const sign = v > 0 ? '+' : '';
  return `${sign}${v.toFixed(digits)}%`;
}

/** Decide rise (positive) / fall (negative) / neutral given a numeric flow. */
function signClass(v: number | null | undefined): 'rise' | 'fall' | 'neutral' {
  if (v === null || v === undefined || v === 0 || Number.isNaN(v)) return 'neutral';
  return v > 0 ? 'rise' : 'fall';
}

/** Composite-score classes — same threshold scheme as the spec (>20 / <-20 / mid). */
function scoreClass(v: number | null | undefined): 'rise' | 'fall' | 'neutral' {
  if (v === null || v === undefined || Number.isNaN(v)) return 'neutral';
  if (v > 20) return 'rise';
  if (v < -20) return 'fall';
  return 'neutral';
}

/** Premium / discount classification (±0.5%). */
function premiumClass(v: number | null | undefined): 'rise' | 'fall' | 'neutral' {
  if (v === null || v === undefined || Number.isNaN(v)) return 'neutral';
  if (v > 0.5) return 'rise';
  if (v < -0.5) return 'fall';
  return 'neutral';
}

/* =============================================================================
 * Row components
 * =========================================================================== */

/** Sparkline cell that lazily fetches the individual-flow history. */
function FlowSparklineCell({ tsCode, days = 30 }: { tsCode: string; days?: number }) {
  const { data, isLoading } = useFundFlowIndividualHistory(tsCode, days);
  if (isLoading) {
    return <Skeleton.Input size="small" active style={{ width: 80, height: 20 }} />;
  }
  const series = (data ?? []).map((p) => p.main_net_inflow);
  if (!series.length) return <span className="ad-text-tertiary">—</span>;
  return <Sparkline data={series} width={80} height={20} />;
}

/** Composite-score breakdown (rendered inside the signals expandable row). */
function ScoreBreakdown({ breakdown }: { breakdown: Record<string, number> }) {
  const entries = Object.entries(breakdown ?? {});
  if (entries.length === 0) {
    return <div className="ad-text-tertiary ad-text-small">无细分数据</div>;
  }
  // Map score contributions to a 0–1 ratio bar. We assume individual drivers are
  // bounded in [-100, 100]; normalise by max-abs for visualisation.
  const maxAbs = entries.reduce((m, [, v]) => Math.max(m, Math.abs(v)), 1);
  return (
    <div className="fund-flow__breakdown">
      {entries.map(([k, v]) => {
        const cls = signClass(v);
        const ratio = Math.min(1, Math.abs(v) / maxAbs);
        return (
          <div key={k} className="fund-flow__breakdown-item">
            <span className="fund-flow__breakdown-label">{k}</span>
            <div className="fund-flow__breakdown-bar">
              <div
                className={`fund-flow__breakdown-bar__fill fund-flow__breakdown-bar__fill--${cls}`}
                style={{ transform: `scaleX(${ratio.toFixed(3)})` }}
              />
            </div>
            <span
              className={`fund-flow__breakdown-value ${
                cls === 'rise'
                  ? 'fund-flow__money--rise'
                  : cls === 'fall'
                  ? 'fund-flow__money--fall'
                  : ''
              }`}
            >
              {v > 0 ? '+' : ''}
              {v.toFixed(1)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** Pct chip next to a money value (used inside a StatCard's `suffix` slot). */
function PctChip({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return (
      <span className="fund-flow__kpi-pct fund-flow__kpi-pct--flat">—</span>
    );
  }
  const cls = value > 0 ? 'rise' : value < 0 ? 'fall' : 'flat';
  return (
    <span className={`fund-flow__kpi-pct fund-flow__kpi-pct--${cls}`}>
      {value > 0 ? '+' : ''}
      {value.toFixed(2)}%
    </span>
  );
}

/* =============================================================================
 * Main page
 * =========================================================================== */

export default function FundFlowPage() {
  const navigate = useNavigate();
  // Injects the shared `.adx-motion` stylesheet (Apple-pattern press/hover).
  useChartMotion();

  // Single shared date — drives market, individual, sector, etf, signals tables.
  const [date, setDate] = useState<Dayjs | null>(null);
  const dateParam = date ? date.format('YYYY-MM-DD') : undefined;

  // Header refresh — invalidate all fund-flow keys.
  const refreshAll = useRefreshFundFlow();

  /* --- Section 1: market KPIs --- */
  const { data: market, isLoading: marketLoading } = useFundFlowMarket(dateParam);

  /* --- Section 2: composite signals Top 20 --- */
  const signalParams = useMemo(
    () => ({
      trade_date: dateParam,
      sort: sortField('composite_score'),
      limit: 20,
    }),
    [dateParam],
  );
  const { data: signalRows = [], isLoading: signalLoading } =
    useFundFlowSignals(signalParams);

  /* --- Tab state (个股 / 板块 / ETF) --- */
  const [tab, setTab] = useState<'individual' | 'sector' | 'etf'>('individual');

  // Individual: per-board sub-tabs.
  const INDIVIDUAL_BOARDS = ['全部', '沪市', '深市', '创业板', '科创板', '北交所'] as const;
  type IndividualBoard = (typeof INDIVIDUAL_BOARDS)[number];
  const BOARD_TO_MARKET: Record<IndividualBoard, string | undefined> = {
    全部: undefined,
    沪市: 'SH',
    深市: 'SZ',
    创业板: 'CYB',
    科创板: 'KCB',
    北交所: 'BJ',
  };
  const [board, setBoard] = useState<IndividualBoard>('全部');
  const marketFilter = BOARD_TO_MARKET[board];

  const [individualSortField, setIndividualSortField] = useState<string | null>(null);
  const individualParams = useMemo(
    () => ({
      trade_date: dateParam,
      sort: individualSortField ?? sortField('main_net_inflow'),
      limit: 50,
      market: marketFilter,
    }),
    [dateParam, individualSortField, marketFilter],
  );
  const { data: individualRows = [], isLoading: individualLoading } =
    useFundFlowIndividual(individualParams);

  // Sector: per-type sub-tabs.
  const SECTOR_TYPES: SectorType[] = ['行业', '概念', '地域'];
  const [sectorType, setSectorType] = useState<SectorType>('行业');
  const sectorParams = useMemo(
    () => ({
      trade_date: dateParam,
      sector_type: sectorType,
      sort: sortField('main_net_inflow'),
    }),
    [dateParam, sectorType],
  );
  const { data: sectorRows = [], isLoading: sectorLoading } =
    useFundFlowSector(sectorParams);

  // ETF list.
  const [etfSortField, setEtfSortField] = useState<string | null>(null);
  const etfParams = useMemo(
    () => ({
      trade_date: dateParam,
      sort: etfSortField ?? sortField('inferred_net_inflow'),
      limit: 50,
    }),
    [dateParam, etfSortField],
  );
  const { data: etfRows = [], isLoading: etfLoading } = useFundFlowEtf(etfParams);

  /* ============================================================
   * Columns
   * ============================================================ */

  const signalColumns: ColumnsType<FlowSignal> = [
    {
      title: '代码',
      dataIndex: 'ts_code',
      key: 'ts_code',
      width: 130,
      render: (_, record) => (
        <InstrumentCodeTag code={record.ts_code} name={record.name ?? undefined} />
      ),
    },
    {
      title: '综合得分',
      dataIndex: 'composite_score',
      key: 'composite_score',
      width: 110,
      sorter: (a, b) => a.composite_score - b.composite_score,
      render: (v: number) => {
        const cls = scoreClass(v);
        return (
          <span className="fund-flow__score-cell">
            <span className={`fund-flow__score-cell__chip fund-flow__score-cell__chip--${cls}`}>
              {v > 0 ? '+' : ''}
              {v.toFixed(1)}
            </span>
          </span>
        );
      },
    },
    {
      title: '主力净流入',
      dataIndex: 'main_net_inflow',
      key: 'main_net_inflow',
      width: 130,
      render: (v: number) => (
        <span className={`fund-flow__money fund-flow__money--${signClass(v)}`}>
          {formatMoney(v)}
        </span>
      ),
    },
    {
      title: '融资变化',
      dataIndex: 'margin_net_change',
      key: 'margin_net_change',
      width: 120,
      render: (v: number) => (
        <span className={`fund-flow__money fund-flow__money--${signClass(v)}`}>
          {formatMoney(v)}
        </span>
      ),
    },
    {
      title: '龙虎榜净买',
      dataIndex: 'lhb_net_buy',
      key: 'lhb_net_buy',
      width: 120,
      render: (v: number) => (
        <span className={`fund-flow__money fund-flow__money--${signClass(v)}`}>
          {formatMoney(v)}
        </span>
      ),
    },
    {
      title: '股东户数变化',
      dataIndex: 'shareholder_count_change',
      key: 'shareholder_count_change',
      width: 130,
      // Fewer shareholders → more concentrated → bullish. Invert the colour cue.
      render: (v: number) => (
        <span className={`fund-flow__money fund-flow__money--${signClass(-v)}`}>
          {formatNumber(v, 0)}
        </span>
      ),
    },
    {
      title: 'AH 溢价',
      dataIndex: 'ah_premium',
      key: 'ah_premium',
      width: 100,
      render: (v: number) => <ReturnTagPct value={v} />,
    },
    {
      title: '大宗交易净买',
      dataIndex: 'block_trade_net',
      key: 'block_trade_net',
      width: 120,
      render: (v: number) => (
        <span className={`fund-flow__money fund-flow__money--${signClass(v)}`}>
          {formatMoney(v)}
        </span>
      ),
    },
    {
      title: '7日趋势',
      key: 'sparkline',
      width: 120,
      render: (_, record) => <FlowSparklineCell tsCode={record.ts_code} days={7} />,
    },
  ];

  const individualColumns: ColumnsType<IndividualFundFlow> = [
    {
      title: '代码',
      dataIndex: 'ts_code',
      key: 'ts_code',
      width: 110,
      fixed: 'left',
      render: (_, record) => (
        <InstrumentCodeTag code={record.ts_code} name={record.name ?? undefined} />
      ),
    },
    {
      title: '主力净流入',
      dataIndex: 'main_net_inflow',
      key: 'main_net_inflow',
      width: 130,
      sorter: (a, b) => a.main_net_inflow - b.main_net_inflow,
      render: (v: number) => (
        <span className={`fund-flow__money fund-flow__money--${signClass(v)}`}>
          {formatMoney(v)}
        </span>
      ),
    },
    {
      title: '主力净占比',
      dataIndex: 'main_net_pct',
      key: 'main_net_pct',
      width: 110,
      render: (v: number) => <ReturnTagPct value={v} />,
    },
    {
      title: '超大单',
      dataIndex: 'super_large_net',
      key: 'super_large_net',
      width: 120,
      render: (v: number) => (
        <span className={`fund-flow__money fund-flow__money--${signClass(v)}`}>
          {formatMoney(v)}
        </span>
      ),
    },
    {
      title: '大单',
      dataIndex: 'large_net',
      key: 'large_net',
      width: 120,
      render: (v: number) => (
        <span className={`fund-flow__money fund-flow__money--${signClass(v)}`}>
          {formatMoney(v)}
        </span>
      ),
    },
    {
      title: '中单',
      dataIndex: 'medium_net',
      key: 'medium_net',
      width: 120,
      render: (v: number) => (
        <span className={`fund-flow__money fund-flow__money--${signClass(v)}`}>
          {formatMoney(v)}
        </span>
      ),
    },
    {
      title: '小单',
      dataIndex: 'small_net',
      key: 'small_net',
      width: 120,
      render: (v: number) => (
        <span className={`fund-flow__money fund-flow__money--${signClass(v)}`}>
          {formatMoney(v)}
        </span>
      ),
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      width: 90,
      render: (v: string) => (
        <Tag color={v === 'akshare' ? 'geekblue' : 'gold'}>{v}</Tag>
      ),
    },
  ];

  const sectorColumns: ColumnsType<SectorFundFlow> = [
    {
      title: '板块',
      dataIndex: 'sector_name',
      key: 'sector_name',
      width: 180,
      fixed: 'left',
    },
    {
      title: '类型',
      dataIndex: 'sector_type',
      key: 'sector_type',
      width: 90,
      render: (v: SectorType) => (
        <ThemeTag variant={v === '行业' ? 'accent' : v === '概念' ? 'default' : 'warning'}>
          {v}
        </ThemeTag>
      ),
    },
    {
      title: '主力净流入',
      dataIndex: 'main_net_inflow',
      key: 'main_net_inflow',
      width: 130,
      sorter: (a, b) => a.main_net_inflow - b.main_net_inflow,
      render: (v: number) => (
        <span className={`fund-flow__money fund-flow__money--${signClass(v)}`}>
          {formatMoney(v)}
        </span>
      ),
    },
    {
      title: '净占比',
      dataIndex: 'main_net_pct',
      key: 'main_net_pct',
      width: 110,
      render: (v: number) => <ReturnTagPct value={v} />,
    },
    {
      title: '超大单',
      dataIndex: 'super_large_net',
      key: 'super_large_net',
      width: 120,
      render: (v: number) => (
        <span className={`fund-flow__money fund-flow__money--${signClass(v)}`}>
          {formatMoney(v)}
        </span>
      ),
    },
    {
      title: '大单',
      dataIndex: 'large_net',
      key: 'large_net',
      width: 120,
      render: (v: number) => (
        <span className={`fund-flow__money fund-flow__money--${signClass(v)}`}>
          {formatMoney(v)}
        </span>
      ),
    },
    {
      title: '领涨股',
      dataIndex: 'leading_stock',
      key: 'leading_stock',
      width: 140,
      ellipsis: true,
    },
  ];

  const etfColumns: ColumnsType<EtfFundFlow> = [
    {
      title: '代码',
      dataIndex: 'ts_code',
      key: 'ts_code',
      width: 110,
      fixed: 'left',
      render: (_, record) => (
        <InstrumentCodeTag code={record.ts_code} name={record.name ?? undefined} />
      ),
    },
    {
      title: '现价',
      dataIndex: 'price',
      key: 'price',
      width: 100,
      sorter: (a, b) => a.price - b.price,
      render: (v: number) => (v != null ? v.toFixed(3) : NULL_PLACEHOLDER),
    },
    {
      title: 'IOPV',
      dataIndex: 'net_value',
      key: 'net_value',
      width: 100,
      render: (v: number) => (v != null ? v.toFixed(3) : NULL_PLACEHOLDER),
    },
    {
      title: '折溢价率',
      dataIndex: 'premium_rate',
      key: 'premium_rate',
      width: 110,
      sorter: (a, b) => a.premium_rate - b.premium_rate,
      render: (v: number) => (
        <span className={`fund-flow__premium fund-flow__premium--${premiumClass(v)}`}>
          {formatPct(v)}
        </span>
      ),
    },
    {
      title: '份额变化（万份）',
      dataIndex: 'shares_change',
      key: 'shares_change',
      width: 140,
      sorter: (a, b) => a.shares_change - b.shares_change,
      render: (v: number) => formatNumber((v ?? 0) / 10000, 0),
    },
    {
      title: '成交额（元）',
      dataIndex: 'turnover',
      key: 'turnover',
      width: 140,
      render: (v: number) => formatNumber(v ?? 0, 0),
    },
    {
      title: '估算净流入',
      dataIndex: 'inferred_net_inflow',
      key: 'inferred_net_inflow',
      width: 140,
      sorter: (a, b) => a.inferred_net_inflow - b.inferred_net_inflow,
      render: (v: number) => (
        <span className={`fund-flow__money fund-flow__money--${signClass(v)}`}>
          {formatMoney(v)}
        </span>
      ),
    },
  ];

  /* ---------- Sort wiring: push sorter result into the API params ---------- */
  const applySortChange = (
    sorter: unknown,
    setField: (v: string | null) => void,
  ) => {
    const s = sorter as { field?: string; order?: string } | undefined;
    if (!s?.field || !s.order) {
      setField(null);
      return;
    }
    setField((s.order === 'ascend' ? '' : '-') + s.field);
  };

  /* ============================================================
   * Render
   * ============================================================ */

  return (
    <div className="adx-motion">
      <PageShell maxWidth="wide">
        <PageHeader
          eyebrow="市场脉搏"
          title="资金流监控"
          description="分位 · 板块 · ETF 资金流向，及综合资金信号排名。数据每日收盘后由 akshare / 东方财富同步。"
          extra={
            <Space>
              <DatePicker
                className="fund-flow__date-picker"
                placeholder="请选择日期"
                value={date}
                onChange={(v) => setDate(v)}
                allowClear
              />
              <Tooltip title="刷新本页所有资金流缓存">
                <Button
                  className="fund-flow__refresh-btn"
                  icon={<ReloadOutlined />}
                  onClick={() => refreshAll()}
                >
                  刷新
                </Button>
              </Tooltip>
            </Space>
          }
        />

        {/* ─────────────────────────────────────────────────────────
            Section 1 — exchange-level KPIs
           ───────────────────────────────────────────────────────── */}
        <SectionHeading
          eyebrow="大盘资金流"
          title="沪深主力资金概览"
          action={
            market?.trade_date ? (
              <ThemeTag variant="default">{market.trade_date}</ThemeTag>
            ) : null
          }
          className="ad-mt-5"
        />
        <Panel padding="md">
          {marketLoading ? (
            <Skeleton active paragraph={{ rows: 4 }} />
          ) : !market ? (
            <EmptyState
              title="暂无大盘资金流数据"
              description={dateParam ? `日期：${dateParam}` : '请等待后台刷新'}
            />
          ) : (
            <div className="fund-flow__kpi-grid responsive-grid responsive-grid--gap-md">
              <StatCard
                title="沪市主力净流入"
                value={
                  <>
                    {formatMoney(market.sh_main_net_inflow)}
                    <PctChip value={market.sh_main_net_pct} />
                  </>
                }
              />
              <StatCard
                title="深市主力净流入"
                value={
                  <>
                    {formatMoney(market.sz_main_net_inflow)}
                    <PctChip value={market.sz_main_net_pct} />
                  </>
                }
              />
              <StatCard
                title="沪深合计净流入"
                value={
                  <>
                    {formatMoney(
                      market.total_main_net_inflow ??
                        (market.sh_main_net_inflow != null && market.sz_main_net_inflow != null
                          ? market.sh_main_net_inflow + market.sz_main_net_inflow
                          : null),
                    )}
                    <PctChip
                      value={
                        market.total_main_net_pct ??
                          (market.sh_main_net_pct != null && market.sz_main_net_pct != null
                            ? market.sh_main_net_pct + market.sz_main_net_pct
                            : null)
                      }
                    />
                  </>
                }
              />
            </div>
          )}
        </Panel>

        {/* ─────────────────────────────────────────────────────────
            Section 2 — composite signals Top 20
           ───────────────────────────────────────────────────────── */}
        <SectionHeading
          eyebrow="综合信号"
          title="资金信号榜 Top 20"
          action={
            <ThemeTag variant="accent">
              <FireOutlined /> 跨源打分
            </ThemeTag>
          }
          className="ad-mt-5"
        />
        <Panel
          padding="none"
          extra={
            <ExportButton
              rows={signalRows as unknown as Record<string, unknown>[]}
              filename={`fundflow-signals-${dateParam ?? 'latest'}`}
              headers={['ts_code', 'name', 'composite_score', 'main_net_inflow', 'margin_net_change', 'lhb_net_buy', 'shareholder_count_change', 'ah_premium', 'block_trade_net']}
              successPrefix="已导出综合信号榜"
            />
          }
        >
          <Table<FlowSignal>
            rowKey="ts_code"
            size="middle"
            columns={signalColumns}
            dataSource={signalRows}
            loading={signalLoading}
            scroll={{ x: 1100 }}
            pagination={false}
            onRow={(record) => ({
              ...clickableRow(() => navigate(`/instruments/${record.ts_code}`)),
              style: { cursor: 'pointer' },
            })}
            expandable={{
              expandedRowRender: (record) => (
                <ScoreBreakdown breakdown={record.score_breakdown ?? {}} />
              ),
              rowExpandable: (record) =>
                !!record.score_breakdown &&
                Object.keys(record.score_breakdown).length > 0,
              expandIcon: ({ expanded, onExpand, record }) =>
                expanded ? null : (
                  <CaretRightOutlined
                    onClick={(e) => {
                      e.stopPropagation();
                      onExpand(record, e);
                    }}
                  />
                ),
            }}
            locale={{
              emptyText: (
                <EmptyState
                  title="暂无综合信号数据"
                  description={`${
                    dateParam ? `日期：${dateParam} · ` : ''
                  }请等待后台刷新或换个日期`}
                />
              ),
            }}
          />
        </Panel>

        {/* ─────────────────────────────────────────────────────────
            Section 3 — tabbed individual / sector / ETF tables
           ───────────────────────────────────────────────────────── */}
        <SectionHeading
          eyebrow="明细"
          title="个股 · 板块 · ETF 资金流向"
          className="ad-mt-5"
        />
        <Panel padding="none">
          <Tabs
            activeKey={tab}
            onChange={(k) => setTab(k as 'individual' | 'sector' | 'etf')}
            className="fund-flow__tabs"
            items={[
              {
                key: 'individual',
                label: (
                  <span className="fund-flow__tab-label">
                    <StockOutlined /> 个股资金流
                    {individualRows.length > 0 ? (
                      <span className="fund-flow__tab-badge">{individualRows.length}</span>
                    ) : null}
                  </span>
                ),
                children: (
                  <div className="fund-flow__tab-panel">
                    <Tabs
                      activeKey={board}
                      onChange={(k) => setBoard(k as IndividualBoard)}
                      size="small"
                      className="fund-flow__sub-tabs"
                      items={INDIVIDUAL_BOARDS.map((b) => ({
                        key: b,
                        label: b,
                      }))}
                    />
                    <div className="ad-flex ad-justify-end ad-mb-2">
                      <ExportButton
                        rows={individualRows as unknown as Record<string, unknown>[]}
                        filename={`fundflow-individual-${board}-${dateParam ?? 'latest'}`}
                        headers={['ts_code', 'name', 'main_net_inflow', 'main_net_pct', 'super_large_net', 'large_net', 'medium_net', 'small_net', 'source']}
                        successPrefix="已导出个股资金流"
                      />
                    </div>
                    <Table<IndividualFundFlow>
                      rowKey={(r) => `${r.trade_date}-${r.ts_code}`}
                      size="middle"
                      columns={individualColumns}
                      dataSource={individualRows}
                      loading={individualLoading}
                      onChange={(_p, _f, sorter) =>
                        applySortChange(sorter, setIndividualSortField)
                      }
                      pagination={{ pageSize: 20, showSizeChanger: false }}
                      scroll={{ x: 900 }}
                      onRow={(record) => ({
                        ...clickableRow(() => navigate(`/instruments/${record.ts_code}`)),
                        style: { cursor: 'pointer' },
                      })}
                      locale={{
                        emptyText: (
                          <EmptyState
                            title={`${board} 个股暂无资金流数据`}
                            description="请尝试切换板块或日期"
                          />
                        ),
                      }}
                    />
                  </div>
                ),
              },
              {
                key: 'sector',
                label: (
                  <span className="fund-flow__tab-label">
                    <AppstoreOutlined /> 板块资金流
                    {sectorRows.length > 0 ? (
                      <span className="fund-flow__tab-badge">{sectorRows.length}</span>
                    ) : null}
                  </span>
                ),
                children: (
                  <div className="fund-flow__tab-panel">
                    <Tabs
                      activeKey={sectorType}
                      onChange={(k) => setSectorType(k as SectorType)}
                      size="small"
                      className="fund-flow__sub-tabs"
                      items={SECTOR_TYPES.map((t) => ({
                        key: t,
                        label: t,
                      }))}
                    />
                    <div className="ad-flex ad-justify-end ad-mb-2">
                      <ExportButton
                        rows={sectorRows as unknown as Record<string, unknown>[]}
                        filename={`fundflow-sector-${sectorType}-${dateParam ?? 'latest'}`}
                        headers={['sector_name', 'sector_type', 'main_net_inflow', 'main_net_pct', 'super_large_net', 'large_net', 'leading_stock']}
                        successPrefix="已导出板块资金流"
                      />
                    </div>
                    <Table<SectorFundFlow>
                      rowKey={(r) => `${r.trade_date}-${r.sector_name}`}
                      size="middle"
                      columns={sectorColumns}
                      dataSource={sectorRows}
                      loading={sectorLoading}
                      pagination={{ pageSize: 20, showSizeChanger: false }}
                      scroll={{ x: 800 }}
                      locale={{
                        emptyText: (
                          <EmptyState
                            title={`${sectorType} 板块暂无资金流数据`}
                            description="请切换板块类型或日期重试"
                          />
                        ),
                      }}
                    />
                  </div>
                ),
              },
              {
                key: 'etf',
                label: (
                  <span className="fund-flow__tab-label">
                    <FundOutlined /> ETF 资金流
                    {etfRows.length > 0 ? (
                      <span className="fund-flow__tab-badge">{etfRows.length}</span>
                    ) : null}
                  </span>
                ),
                children: (
                  <div className="fund-flow__tab-panel">
                    <div className="ad-flex ad-justify-end ad-mb-2">
                      <ExportButton
                        rows={etfRows as unknown as Record<string, unknown>[]}
                        filename={`fundflow-etf-${dateParam ?? 'latest'}`}
                        headers={['ts_code', 'name', 'price', 'net_value', 'premium_rate', 'shares_change', 'turnover', 'inferred_net_inflow']}
                        successPrefix="已导出 ETF 资金流"
                      />
                    </div>
                    <Table<EtfFundFlow>
                      rowKey={(r) => `${r.trade_date}-${r.ts_code}`}
                      size="middle"
                      columns={etfColumns}
                      dataSource={etfRows}
                      loading={etfLoading}
                      onChange={(_p, _f, sorter) => applySortChange(sorter, setEtfSortField)}
                      pagination={{ pageSize: 20, showSizeChanger: false }}
                      scroll={{ x: 900 }}
                      onRow={(record) => ({
                        ...clickableRow(() => navigate(`/instruments/${record.ts_code}`)),
                        style: { cursor: 'pointer' },
                      })}
                      locale={{
                        emptyText: (
                          <EmptyState
                            title="ETF 暂无资金流数据"
                            description="折溢价率基于 IOPV 与现价估算"
                          />
                        ),
                      }}
                    />
                  </div>
                ),
              },
            ]}
          />
        </Panel>

        {/* ─────────────────────────────────────────────────────────
            Section 4 — disclosure block
           ───────────────────────────────────────────────────────── */}
        <Panel variant="minimal" className="ad-mt-5" padding="md">
          <Collapse
            ghost
            expandIcon={({ isActive }) => (
              <CaretRightOutlined rotate={isActive ? 90 : 0} />
            )}
            items={[
              {
                key: 'sources',
                label: (
                  <span className="ad-text-small">
                    <ExperimentOutlined /> 数据来源与说明
                  </span>
                ),
                children: (
                  <div className="fund-flow__sources">
                    <div className="fund-flow__source">
                      <div className="fund-flow__source-title">
                        <RiseOutlined /> 东方财富（eastmoney）
                      </div>
                      <div className="fund-flow__source-desc">
                        提供大盘主力资金 / 个股超大单大单中单小单拆分；盘中 5 分钟刷新一次。
                      </div>
                    </div>
                    <div className="fund-flow__source">
                      <div className="fund-flow__source-title">
                        <FallOutlined /> AkShare
                      </div>
                      <div className="fund-flow__source-desc">
                        提供 ETF 份额变化、IOPV 与个股资金流，同源去重后入库。
                      </div>
                    </div>
                    <div className="fund-flow__source">
                      <div className="fund-flow__source-title">
                        <ExperimentOutlined /> 交易所公开披露
                      </div>
                      <div className="fund-flow__source-desc">
                        龙虎榜、大宗交易、融资融券为沪深交易所收盘后披露的官方数据。
                      </div>
                    </div>
                    <div className="fund-flow__source">
                      <div className="fund-flow__source-title">
                        <FireOutlined /> 综合信号评分规则
                      </div>
                      <div className="fund-flow__source-desc">
                        资金流 + 融资变化 + 龙虎榜 + 股东户数 + AH 溢价 + 大宗交易
                        线性加权，截断在 [-100, +100]。
                      </div>
                    </div>
                  </div>
                ),
              },
            ]}
          />
        </Panel>
      </PageShell>
    </div>
  );
}

// Re-export dayjs so the date picker import is never flagged as unused by TS noUnused checks.
export const _dayjsBrand = dayjs;
