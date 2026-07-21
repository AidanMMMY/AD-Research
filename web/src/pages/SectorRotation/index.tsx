import { useEffect, useMemo, useState } from 'react';
import { Alert, Segmented, Select, Table, Tabs, Tag, Tooltip } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import {
  useSectorConstituents,
  useSectorList,
  useSectorRotation,
} from '@/hooks/useSectorRotation';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import EmptyState from '@/components/EmptyState';
import HelpPopover from '@/components/HelpPopover';
import LastUpdated from '@/components/LastUpdated';
import LoadingBlock from '@/components/LoadingBlock';
import ReturnTag from '@/components/ReturnTag';
import ThemeTag from '@/components/ThemeTag';
import { useSettingsStore } from '@/stores/settings';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';
import { useChartMotion } from '@/hooks/useChartMotion';
import { getReturnColor } from '@/utils/color';
import { readCssVar, resolveChartColors } from '@/utils/cssVar';
import { subscribeChartThemeCache } from '@/utils/chartColors';
import type {
  SectorClassification,
  SectorConstituent,
  SectorPerformance,
  SectorReturnPeriod,
} from '@/types/sector_rotation';
import { SECTOR_RETURN_LABELS, SECTOR_RETURN_PERIODS } from '@/types/sector_rotation';
import './styles.css';

// ---------------------------------------------------------------------------
// Phase 3 ReturnTag wrapper
// ---------------------------------------------------------------------------
// 官方指数回报下，hover 时显示等权回报作为对照；GICS / fallback 模式
// 直接透传 ReturnTag。
// ---------------------------------------------------------------------------

const CONSTITUENT_RETURN_KEY: Record<SectorReturnPeriod, keyof SectorPerformance> = {
  '1w': 'constituent_return_1w',
  '1m': 'constituent_return_1m',
  '3m': 'constituent_return_3m',
  '6m': 'constituent_return_6m',
  '1y': 'constituent_return_1y',
};

function formatPct(v: number | null | undefined): string {
  if (v == null) return '—';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${(v * 100).toFixed(2)}%`;
}

function Phase3ReturnTag({
  value,
  sector,
  period,
}: {
  value: number;
  sector: SectorPerformance;
  period: SectorReturnPeriod;
}) {
  // SW 模式 + 官方指数 + 有等权对照：hover 显示
  if (
    sector.return_source === 'official_index' &&
    sector.sw_l1_code
  ) {
    const eqField = CONSTITUENT_RETURN_KEY[period];
    const eqValue = sector[eqField] as number | null | undefined;
    const tooltip = (
      <div style={{ lineHeight: 1.6 }}>
        <div>
          申万一级指数 <strong>{sector.sw_l1_code}</strong> 官方回报
        </div>
        {eqValue != null && (
          <div>
            等权 ETF+STOCK 回报对照：
            <strong style={{ color: eqValue >= 0 ? 'var(--color-rise, #ef232a)' : 'var(--color-fall, #14b143)' }}>
              {' '}
              {formatPct(eqValue)}
            </strong>
          </div>
        )}
      </div>
    );
    return (
      <Tooltip title={tooltip} mouseEnterDelay={0.1}>
        <span style={{ cursor: 'help' }}>
          <ReturnTag value={value} />
        </span>
      </Tooltip>
    );
  }
  return <ReturnTag value={value} />;
}

const PERIOD_RETURN_KEY: Record<SectorReturnPeriod, keyof SectorPerformance> = {
  '1w': 'return_1w',
  '1m': 'return_1m',
  '3m': 'return_3m',
  '6m': 'return_6m',
  '1y': 'return_1y',
};

/**
 * Normalise a CSS variable colour ("var(--color-rise)") to its terminal
 * hex fallback for ECharts (which can't resolve CSS vars inside dynamic
 * style props). Falls back to the chart palette utility.
 */
function toEChartsColor(cssVarRef: string, fallback: string): string {
  const [resolved] = resolveChartColors([cssVarRef], [fallback]);
  return resolved;
}

/**
 * Compute a dynamic visualMap domain for the multi-period return heatmap.
 * dataviz P0-3: hard-coded ±6% clamps everything to mid-tone in normal
 * markets and saturates the gradient in bull/bear markets. Use 2σ around
 * the observed mean as the default and fall back to ±3% only when data is
 * too sparse / flat to estimate a meaningful std.
 */
function computeHeatmapDomain(
  sectors: SectorPerformance[],
): { min: number; max: number } {
  const FALLBACK = { min: -3, max: 3 };

  const values: number[] = [];
  sectors.forEach((s) => {
    SECTOR_RETURN_PERIODS.forEach((period) => {
      const key = PERIOD_RETURN_KEY[period];
      const v = Number(s[key] ?? 0);
      if (Number.isFinite(v)) values.push(v);
    });
  });

  if (values.length < 2) return FALLBACK;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const mean = values.reduce((sum, v) => sum + v, 0) / values.length;
  const variance =
    values.reduce((sum, v) => sum + (v - mean) ** 2, 0) / values.length;
  const std = Math.sqrt(variance);

  // Std too small (flat data or single value) — fall back to a symmetric
  // ±3% which keeps the gradient useful without crushing contrast.
  if (std < 0.1) return FALLBACK;

  // 2σ around mean, but always honour the observed extremes so no
  // saturated cell gets clipped beyond the gradient's end-stop.
  let lo = Math.min(mean - 2 * std, min);
  let hi = Math.max(mean + 2 * std, max);

  // Round to nearest 0.5 for cleaner visualMap tick labels.
  lo = Math.floor(lo * 2) / 2;
  hi = Math.ceil(hi * 2) / 2;

  // Guard against degenerate ranges.
  if (hi - lo < 1) {
    const mid = (hi + lo) / 2;
    return { min: mid - 1.5, max: mid + 1.5 };
  }

  return { min: lo, max: hi };
}

// Detail-panel tab keys (板块汇总 / 成份股构成).
type DetailTab = 'summary' | 'constituents';

export default function SectorRotation() {
  const mode = useSettingsStore((s) => s.mode);
  const prefersReducedMotion = usePrefersReducedMotion();
  // Injects the shared `.adx-motion` stylesheet (Apple-pattern press/hover).
  useChartMotion();
  // Industry taxonomy toggle: 申万一级 (default, A-share) vs GICS (global).
  const [classification, setClassification] = useState<SectorClassification>('SW');
  const clsLabel = classification === 'SW' ? '申万一级' : 'GICS';
  const { data, isLoading, isFetching, dataUpdatedAt } = useSectorRotation(
    undefined,
    undefined,
    classification,
  );
  // Sector list (for the constituents tab's dropdown).
  const { data: sectorsData } = useSectorList(classification);
  // Detail-panel tab (板块汇总 / 成份股构成).
  const [detailTab, setDetailTab] = useState<DetailTab>('summary');
  // Re-render when the theme toggles so chart colours pick up new vars.
  const [themeTick, setThemeTick] = useState(0);
  useEffect(
    () => subscribeChartThemeCache(() => setThemeTick((t) => t + 1)),
    [],
  );

  const sectors = data?.sectors || [];
  const isMobile = useIsMobile();
  // Responsive heatmap height: give each sector row enough breathing room.
  // Margins ~82px (grid top+bottom) + labels; mobile allows vertical scroll.
  const heatmapHeight = isMobile
    ? Math.max(480, 82 + sectors.length * 16)
    : Math.max(720, 82 + sectors.length * 22);
  const signals = data?.rotation_signals || [];
  const marketAvg = data?.market_avg;
  const scope = data?.scope;

  // Pre-resolve palette for heatmap once per render.
  const palette = useMemo(() => {
    const upHex = readCssVar('--color-rise', '#c96b6b');
    const downHex = readCssVar('--color-fall', '#5fa87a');
    const textPrimary = toEChartsColor('var(--text-primary)', '#1f1f1f');
    const textSecondary = toEChartsColor('var(--text-secondary)', '#666666');
    const border = toEChartsColor('var(--border-default)', 'rgba(0,0,0,0.08)');
    const bgBase = toEChartsColor('var(--bg-elevated)', '#ffffff');
    const midHex = toEChartsColor('var(--bg-elevated)', '#f4f4f0');
    return { upHex, downHex, textPrimary, textSecondary, border, bgBase, midHex };
  }, [themeTick]);

  // ------------------ Charts ------------------

  /** Horizontal bar — sectors ranked by 1m return (best on top). */
  const rankOption: EChartsOption = useMemo(() => {
    const ordered = [...sectors].reverse(); // ECharts draws first at the bottom
    return {
      // Reduced motion: drop the canvas animation so the chart appears
      // instantly without re-drawing every paint frame.
      animation: !prefersReducedMotion,
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        backgroundColor: palette.bgBase,
        textStyle: { color: palette.textPrimary },
      },
      grid: { left: 130, right: 32, top: 20, bottom: 28 },
      xAxis: {
        type: 'value',
        axisLabel: { formatter: '{value}%', color: palette.textSecondary },
        splitLine: { lineStyle: { color: palette.border } },
      },
      yAxis: {
        type: 'category',
        data: ordered.map((s) => s.sector),
        axisLabel: { color: palette.textPrimary, fontSize: 12 },
      },
      series: [
        {
          type: 'bar',
          data: ordered.map((s) => ({
            value: s.return_1m,
            itemStyle: {
              color: s.return_1m >= 0 ? palette.upHex : palette.downHex,
              opacity: 0.85,
            },
          })),
          label: {
            show: true,
            formatter: (params: any) => {
              const v = Number(params?.value ?? 0);
              // sector returns are decimals (e.g. 0.025 = +2.5%); multiply by 100 before display.
              return `${(v * 100).toFixed(2)}%`;
            },
            fontSize: 11,
            color: palette.textPrimary,
            position: 'right',
          },
        },
      ],
    };
  }, [sectors, palette, prefersReducedMotion]);

  /** Heatmap: rows = sectors, cols = [1w, 1m, 3m, 6m, 1y], colour = return. */
  const heatmapOption: EChartsOption = useMemo(() => {
    const ordered = [...sectors].sort((a, b) => b.return_1m - a.return_1m);
    const data: [number, number, number][] = [];
    ordered.forEach((s, rowIdx) => {
      SECTOR_RETURN_PERIODS.forEach((period, colIdx) => {
        const key = PERIOD_RETURN_KEY[period];
        const v = Number(s[key] ?? 0);
        data.push([colIdx, rowIdx, Number(v.toFixed(2))]);
      });
    });
    // dataviz P0-3: dynamic visualMap domain — see computeHeatmapDomain above.
    const { min: vmMin, max: vmMax } = computeHeatmapDomain(ordered);
    return {
      // Reduced motion: skip the canvas animation; the cells simply appear.
      animation: !prefersReducedMotion,
      tooltip: {
        position: 'top',
        formatter: (p: any) => {
          const [c, r, v] = p.value as [number, number, number];
          const sector = ordered[r]?.sector ?? '';
          const period = SECTOR_RETURN_LABELS[SECTOR_RETURN_PERIODS[c]];
          return `${sector} · ${period}<br/><b>${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%</b>`;
        },
      },
      grid: { left: 150, right: 30, top: 32, bottom: 50 },
      xAxis: {
        type: 'category',
        data: SECTOR_RETURN_PERIODS.map((p) => SECTOR_RETURN_LABELS[p]),
        splitArea: { show: true },
        axisLabel: { color: palette.textPrimary, fontSize: 12 },
      },
      yAxis: {
        type: 'category',
        data: ordered.map((s) => s.sector),
        splitArea: { show: true },
        axisLabel: { color: palette.textPrimary, fontSize: 12 },
      },
      visualMap: {
        min: vmMin,
        max: vmMax,
        calculable: true,
        orient: 'horizontal',
        left: 'center',
        bottom: 6,
        text: [`+${(vmMax * 100).toFixed(1)}%`, `${(vmMin * 100).toFixed(1)}%`],
        textStyle: { color: palette.textSecondary, fontSize: 11 },
        inRange: { color: [palette.downHex, palette.midHex, palette.upHex] },
        itemWidth: 12,
        itemHeight: 80,
      },
      series: [
        {
          type: 'heatmap',
          data,
          label: {
            show: true,
            formatter: (p: any) => {
              const v = p.value[2] as number;
              // Heatmap values come from etf_indicator.return_* (decimals); ×100 before display.
              return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`;
            },
            fontSize: 11,
            color: palette.textPrimary,
          },
          itemStyle: {
            borderColor: palette.border,
            borderWidth: 1,
          },
        },
      ],
    };
  }, [sectors, palette, prefersReducedMotion]);

  /** Relative-strength bar — quick view of who is beating the market. */
  const rsOption: EChartsOption = useMemo(() => {
    return {
      // Reduced motion: drop the canvas animation for the bar enter.
      animation: !prefersReducedMotion,
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: any) => {
          const p = Array.isArray(params) ? params[0] : params;
          const v = Number(p?.value ?? 0);
          return `${p?.name ?? ''}<br/>1月超额收益: <b>${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%</b>`;
        },
      },
      grid: { left: 130, right: 32, top: 20, bottom: 32 },
      xAxis: {
        type: 'value',
        name: '相对强弱',
        nameTextStyle: { color: palette.textSecondary, padding: [0, 0, 0, -40] },
        axisLabel: { color: palette.textSecondary },
        splitLine: { lineStyle: { color: palette.border } },
      },
      yAxis: {
        type: 'category',
        data: [...sectors].reverse().map((s) => s.sector),
        axisLabel: { color: palette.textPrimary, fontSize: 11 },
      },
      series: [
        {
          type: 'bar',
          data: [...sectors].reverse().map((s) => ({
            value: Number(s.relative_strength_1m.toFixed(2)),
            itemStyle: {
              color:
                s.relative_strength_1m >= 0 ? palette.upHex : palette.downHex,
              opacity: 0.85,
            },
          })),
          label: {
            show: true,
            formatter: (params: any) => Number(params?.value ?? 0).toFixed(2),
            fontSize: 11,
            color: palette.textPrimary,
            position: 'right',
          },
          markLine: {
            symbol: 'none',
            data: [
              {
                xAxis: 0,
                label: {
                  formatter: '市场基准 = 0',
                  color: palette.textSecondary,
                },
                lineStyle: {
                  color: palette.textSecondary,
                  type: 'dashed',
                },
              },
            ],
          },
        },
      ],
    };
  }, [sectors, palette, prefersReducedMotion]);

  // ------------------ Table ------------------

  const columns = [
    {
      title: <HelpPopover termKey="momentum_rank" mode={mode}>排名</HelpPopover>,
      dataIndex: 'momentum_rank',
      width: 60,
      render: (v: number) => (
        <span className="font-mono ad-table-accent">{v}</span>
      ),
    },
    {
      title: `行业板块 (${clsLabel})`,
      dataIndex: 'sector',
      width: 220,
      render: (v: string, r: SectorPerformance) => (
        <div className="ad-stack-xs">
          <span className="ad-table-text-primary">
            {v}
            {r.return_source === 'official_index' && (
              <Tag
                color="blue"
                style={{ marginLeft: 6, fontSize: 10, lineHeight: '14px', padding: '0 4px' }}
                title={`申万一级指数 ${r.sw_l1_code ?? ''} 当日收盘 ${
                  r.official_close != null
                    ? r.official_close.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
                    : '—'
                }`}
              >
                官方
              </Tag>
            )}
            {r.return_source === 'constituents_equal_weight' && r.sw_l1_code && (
              <Tag
                color="default"
                style={{ marginLeft: 6, fontSize: 10, lineHeight: '14px', padding: '0 4px' }}
                title={`申万一级 ${r.sw_l1_code} 暂无官方指数回报,当前显示等权 ETF+STOCK 回报`}
              >
                等权
              </Tag>
            )}
          </span>
          <span className="ad-table-text-secondary">
            {r.stock_count} 只个股 / {r.etf_count} 只 ETF
          </span>
        </div>
      ),
    },
    {
      title: <HelpPopover termKey="return_1w" mode={mode}>1周</HelpPopover>,
      dataIndex: 'return_1w',
      width: 90,
      render: (v: number, r: SectorPerformance) => (
        <Phase3ReturnTag value={v} sector={r} period="1w" />
      ),
    },
    {
      title: <HelpPopover termKey="return_1m" mode={mode}>1月</HelpPopover>,
      dataIndex: 'return_1m',
      width: 90,
      render: (v: number, r: SectorPerformance) => (
        <Phase3ReturnTag value={v} sector={r} period="1m" />
      ),
    },
    {
      title: <HelpPopover termKey="return_3m" mode={mode}>3月</HelpPopover>,
      dataIndex: 'return_3m',
      width: 90,
      render: (v: number, r: SectorPerformance) => (
        <Phase3ReturnTag value={v} sector={r} period="3m" />
      ),
    },
    {
      title: <HelpPopover termKey="return_6m" mode={mode}>6月</HelpPopover>,
      dataIndex: 'return_6m',
      width: 90,
      render: (v: number, r: SectorPerformance) => (
        <Phase3ReturnTag value={v} sector={r} period="6m" />
      ),
    },
    {
      title: <HelpPopover termKey="return_1y" mode={mode}>1年</HelpPopover>,
      dataIndex: 'return_1y',
      width: 90,
      render: (v: number, r: SectorPerformance) => (
        <Phase3ReturnTag value={v} sector={r} period="1y" />
      ),
    },
    {
      title: <HelpPopover termKey="sharpe_1y" mode={mode}>夏普</HelpPopover>,
      dataIndex: 'sharpe_1y',
      width: 80,
      render: (v: number) => (
        <span className="font-mono ad-table-mono">{v.toFixed(2)}</span>
      ),
    },
    {
      title: <HelpPopover termKey="rsi14" mode={mode}>RSI</HelpPopover>,
      dataIndex: 'rsi14',
      width: 70,
      render: (v: number) => (
        <span className="font-mono ad-table-mono">{v.toFixed(0)}</span>
      ),
    },
    {
      title: <HelpPopover termKey="relative_strength" mode={mode}>相对强弱（超额收益）</HelpPopover>,
      dataIndex: 'relative_strength_1m',
      width: 110,
      render: (v: number) => {
        let variant: 'rise' | 'fall' | 'neutral' = 'neutral';
        if (v > 0) variant = 'rise';
        if (v < 0) variant = 'fall';
        return <ThemeTag variant={variant}>{((v ?? 0) * 100).toFixed(2)}%</ThemeTag>;
      },
    },
  ];

  // ------------------ Render ------------------

  const showSkeleton = isLoading && !data;
  const totalInstruments = sectors.reduce((sum, s) => sum + s.count, 0);
  const stockCount = sectors.reduce((sum, s) => sum + s.stock_count, 0);
  const etfCount = sectors.reduce((sum, s) => sum + s.etf_count, 0);

  return (
    <div className="adx-motion">
      <PageShell maxWidth="wide">
        <PageHeader
          eyebrow="行业研究"
        title="行业板块轮动"
        description={`基于${clsLabel}行业分类的 A 股板块表现跟踪，相对强弱与轮动信号`}
        tutorial={
          <span>
            按行业板块（{clsLabel}）查看 A 股个股 + ETF 的整体表现：左侧是动量排名，中间是各周期收益热力图，右下角是相对强弱。出现「轮动信号」说明该板块最近一周（5 个交易日）排名变化 ≥3 位。
          </span>
        }
        extra={
          <div className="ad-flex ad-flex-wrap ad-items-center ad-gap-3 sector-rotation__header-extra">
            <Segmented<SectorClassification>
              size="small"
              value={classification}
              onChange={(v) => setClassification(v)}
              options={[
                { label: 'GICS', value: 'GICS' },
                { label: '申万一级', value: 'SW' },
              ]}
            />
            <LastUpdated
              at={dataUpdatedAt}
              loading={isFetching && !data}
            />
          </div>
        }
      />

      {/* Scope banner: clearly state what is and isn't included. */}
      <Panel variant="minimal" padding="sm" className="ad-mb-4">
        <div className="ad-info-banner">
          <InfoCircleOutlined className="ad-info-banner__icon" />
          <div className="ad-info-banner__body">
            <span className="ad-info-banner__title">当前范围</span>
            <span className="ad-info-banner__text">
              仅纳入 A 股（沪深北）<b>个股 + ETF</b>，分类体系为
              <Tag color={classification === 'SW' ? 'gold' : 'default'} className="sector-rotation__scope-tag">
                {classification === 'SW' ? '申万一级行业' : 'GICS 行业'}
              </Tag>
              数字币 / 美股 / 港股 不参与本轮动分析。
              {scope?.classification === 'SW' ? (
                <span className="sector-rotation__scope-source">
                  分类来源：<code className="font-mono">etf_info.sw_l1</code>
                  （个股由 Tushare 申万成分 / CSRC→申万 映射，ETF 由 sub_category/underlying_index 启发式匹配）。
                </span>
              ) : (
                scope?.classification && (
                  <span className="sector-rotation__scope-source">
                    分类来源：<code className="font-mono">etf_info.sector</code>
                    （个股由 CSRC→GICS 映射，ETF 由 sub_category/underlying_index 启发式匹配）。
                  </span>
                )
              )}
            </span>
          </div>
        </div>
      </Panel>

      {/* Phase 3 数据源分布 — 仅 SW 分类下展示 */}
      {classification === 'SW' && sectors.length > 0 && (
        <div
          className="ad-callout ad-mb-3"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            flexWrap: 'wrap',
            padding: '10px 14px',
            borderRadius: 8,
            background: 'var(--color-surface-soft, rgba(0,0,0,0.03))',
            fontSize: 12,
          }}
        >
          <span style={{ color: 'var(--color-text-secondary, #666)' }}>
            <strong>Phase 3 官方指数回报：</strong>
            {sectors.filter((s) => s.return_source === 'official_index').length}
            {' '}/ {sectors.length} 行业
          </span>
          {sectors.some((s) => s.return_source === 'official_index') && (
            <span style={{ color: 'var(--color-text-tertiary, #999)' }}>
              · 鼠标悬停 1周/1月/3月/6月/1年 回报格查看等权 ETF+STOCK 对照
            </span>
          )}
        </div>
      )}

      {/* Headline metrics */}
      <div className="ad-metric-strip ad-metric-strip--cols-4 ad-mb-5">
        <div className="ad-metric-item">
          <div className="ad-metric-item__label">分析日期</div>
          <div className="ad-metric-item__value">{data?.trade_date || '—'}</div>
        </div>
        <div className="ad-metric-item">
          <div className="ad-metric-item__label">市场平均 1月</div>
          <div
            className="ad-metric-item__value ad-metric-item__value--colored"
            style={{ color: getReturnColor(marketAvg?.return_1m ?? 0) }}
          >
            {((marketAvg?.return_1m ?? 0) * 100).toFixed(2)}
            <span className="ad-metric-item__suffix">%</span>
          </div>
        </div>
        <div className="ad-metric-item">
          <div className="ad-metric-item__label">行业板块数</div>
          <div className="ad-metric-item__value">{sectors.length}</div>
        </div>
        <div className="ad-metric-item">
          <div className="ad-metric-item__label">纳入标的</div>
          <div className="ad-metric-item__value">
            {totalInstruments}
            <span className="ad-metric-item__suffix">
              {' '}
              ({stockCount}股 / {etfCount}基)
            </span>
          </div>
        </div>
      </div>

      {/* Rotation signals */}
      {signals.length > 0 && (
        <Panel
          title={<HelpPopover termKey="rotation_signal" mode={mode}>轮动信号</HelpPopover>}
          variant="default"
          className="ad-mb-4"
        >
          <div className="sector-rotation__signal-grid">
            {signals.map((signal, idx) => (
              <Alert
                key={`${signal.sector}-${idx}`}
                message={
                  <div className="sector-rotation__signal-row">
                    <span
                      className="sector-rotation__signal-sector"
                      title={signal.sector}
                    >
                      {signal.sector}
                    </span>
                    <span className="sector-rotation__signal-meta">
                      <span
                        className={`sector-rotation__signal-indicator ${
                          signal.type === 'up'
                            ? 'sector-rotation__signal-up'
                            : 'sector-rotation__signal-down'
                        }`}
                      >
                        {signal.type === 'up' ? '↑' : '↓'} {Math.abs(signal.rank_change)} 位
                      </span>
                      <span className="sector-rotation__signal-ranks">
                        #{signal.previous_rank} → #{signal.current_rank}
                      </span>
                    </span>
                  </div>
                }
                type={signal.type === 'up' ? 'success' : 'warning'}
                showIcon
              />
            ))}
          </div>
        </Panel>
      )}

      {/* Charts row 1 — ranking + relative strength */}
      <div className="ad-mb-4">
        <ResponsiveGrid cols={2} gap="md" className="sector-rotation__charts-row">
          <Panel
            title="行业板块 1月收益排名"
            extra={
              <span className="ad-table-text-secondary sector-rotation__chart-hint">
                按 1月平均收益降序
              </span>
            }
            variant="default"
            className="sector-rotation__chart-panel"
          >
            <div className="ad-chart-container sector-rotation__chart-container">
              {showSkeleton ? (
                <div className="sector-rotation__chart-loader">
                  <LoadingBlock size="sm" />
                </div>
              ) : sectors.length === 0 ? (
                <EmptyState
                  title="暂无板块数据"
                  description={`当前 A 股范围内无${clsLabel}板块数据，请稍后重试或检查 ETL。`}
                />
              ) : (
                <ReactECharts option={rankOption} role="img" aria-label="行业轮动排名" />
              )}
            </div>
          </Panel>
          <Panel
            title="行业相对强弱 (vs 市场平均)"
            extra={
              <span className="ad-table-text-secondary sector-rotation__chart-hint">
                1月超额收益 = 板块收益 - 市场平均
              </span>
            }
            variant="default"
            className="sector-rotation__chart-panel"
          >
            <div className="ad-chart-container sector-rotation__chart-container">
              {showSkeleton ? (
                <div className="sector-rotation__chart-loader">
                  <LoadingBlock size="sm" />
                </div>
              ) : sectors.length === 0 ? (
                <EmptyState
                  title="暂无板块数据"
                  description={`当前 A 股范围内无${clsLabel}板块数据。`}
                />
              ) : (
                <ReactECharts option={rsOption} role="img" aria-label="相对强弱图" />
              )}
            </div>
          </Panel>
        </ResponsiveGrid>
      </div>

      {/* Heatmap — multi-period returns by sector */}
      <div className="ad-mb-4">
        <Panel
          title="多周期收益热力图"
          extra={
            <span className="ad-table-text-secondary sector-rotation__chart-hint">
              行：{clsLabel}板块 · 列：收益周期 · 色：涨跌强度
            </span>
          }
          variant="default"
        >
          {showSkeleton ? (
            <LoadingBlock size="sm" />
          ) : sectors.length === 0 ? (
            <EmptyState
              title="暂无板块数据"
              description={`当前 A 股范围内无${clsLabel}板块数据。`}
            />
          ) : (
            <div
              className="ad-chart-container sector-rotation__heatmap-container"
              style={{ height: heatmapHeight, minHeight: heatmapHeight }}
            >
              <ReactECharts option={heatmapOption} role="img" aria-label="相关性热力图" />
            </div>
          )}
        </Panel>
      </div>

      {/* Detail panel — split into 板块汇总 + 成份股构成 tabs */}
      <Panel
        title="行业板块详细数据"
        variant="default"
        padding="none"
        className="sector-rotation__detail-panel"
      >
        <Tabs
          className="ad-px-4"
          activeKey={detailTab}
          onChange={(k) => setDetailTab(k as DetailTab)}
          items={[
            { key: 'summary', label: '板块汇总' },
            { key: 'constituents', label: '成份股构成' },
          ]}
        />
        {detailTab === 'summary' ? (
          <div className="ad-table-scroll ad-table-sticky ad-px-4 ad-pb-4">
            <Table
              dataSource={sectors}
              columns={columns}
              rowKey="sector"
              size="small"
              scroll={{ x: 'max-content' }}
              pagination={false}
              loading={isLoading}
            />
          </div>
        ) : (
          <ConstituentsTab
            defaultSector={
              sectors[0]?.sector ?? sectorsData?.items?.[0]?.sector ?? null
            }
            sectors={sectorsData?.items ?? []}
            classification={classification}
          />
        )}
      </Panel>
      </PageShell>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Constituents tab — top-N instruments inside a selected sector (STOCK + ETF).
// ---------------------------------------------------------------------------

function ConstituentsTab({
  defaultSector,
  sectors,
  classification,
}: {
  defaultSector: string | null;
  sectors: { sector: string; stock_count: number; etf_count: number }[];
  classification: SectorClassification;
}) {
  const [selectedSector, setSelectedSector] = useState<string | null>(
    defaultSector,
  );
  const [topN, setTopN] = useState<number>(20);

  // Re-sync when the upstream defaultSector changes (e.g. data reload) or
  // when the taxonomy switches and the selected sector no longer exists in
  // the new list (GICS names differ from 申万 names).
  useEffect(() => {
    if (
      sectors.length > 0 &&
      selectedSector &&
      !sectors.some((s) => s.sector === selectedSector)
    ) {
      setSelectedSector(defaultSector);
    } else if (defaultSector && !selectedSector) {
      setSelectedSector(defaultSector);
    }
  }, [defaultSector, selectedSector, sectors]);

  const { data, isLoading, isFetching } = useSectorConstituents(
    selectedSector,
    topN,
    undefined,
    classification,
  );

  const items = data?.items ?? [];
  const sectorMeta = sectors.find((s) => s.sector === selectedSector);

  const constituentsColumns = useMemo(
    () => [
      {
        title: '代码',
        dataIndex: 'code',
        width: 110,
        render: (v: string) => <span className="font-mono ad-table-accent">{v}</span>,
      },
      {
        title: '名称',
        dataIndex: 'name',
        width: 180,
        render: (v: string) => (
          <div className="ad-stack-xs">
            <span className="ad-table-text-primary">{v}</span>
            {sectorMeta && (
              <span className="ad-table-text-secondary">
                {sectorMeta.stock_count}股 / {sectorMeta.etf_count}基
              </span>
            )}
          </div>
        ),
      },
      {
        title: '类型',
        dataIndex: 'instrument_type',
        width: 80,
        render: (v: SectorConstituent['instrument_type']) =>
          v === 'STOCK' ? (
            <Tag color="blue">个股</Tag>
          ) : (
            <Tag color="purple">ETF</Tag>
          ),
      },
      {
        title: (
          <span>
            权重 (元)
            <span className="ad-table-text-secondary sector-rotation__weight-label">
              {items[0]?.weight_label === '规模' ? '· 规模' : '· 市值'}
            </span>
          </span>
        ),
        dataIndex: 'weight',
        width: 150,
        align: 'right' as const,
        sorter: (a: SectorConstituent, b: SectorConstituent) =>
          (a.weight ?? -Infinity) - (b.weight ?? -Infinity),
        render: (v: number | null) =>
          v == null ? (
            <span className="ad-table-text-secondary">—</span>
          ) : (
            <span className="font-mono ad-table-mono">{formatWeight(v)}</span>
          ),
      },
      {
        title: '1周',
        dataIndex: 'return_1w',
        width: 80,
        render: (v: number | null) =>
          v == null ? <span className="ad-table-text-secondary">—</span> : <ReturnTag value={v} />,
      },
      {
        title: '1月',
        dataIndex: 'return_1m',
        width: 80,
        render: (v: number | null) =>
          v == null ? <span className="ad-table-text-secondary">—</span> : <ReturnTag value={v} />,
      },
      {
        title: '3月',
        dataIndex: 'return_3m',
        width: 80,
        render: (v: number | null) =>
          v == null ? <span className="ad-table-text-secondary">—</span> : <ReturnTag value={v} />,
      },
      {
        title: '6月',
        dataIndex: 'return_6m',
        width: 80,
        render: (v: number | null) =>
          v == null ? <span className="ad-table-text-secondary">—</span> : <ReturnTag value={v} />,
      },
      {
        title: '1年',
        dataIndex: 'return_1y',
        width: 80,
        render: (v: number | null) =>
          v == null ? <span className="ad-table-text-secondary">—</span> : <ReturnTag value={v} />,
      },
      {
        title: '夏普',
        dataIndex: 'sharpe_1y',
        width: 70,
        render: (v: number | null) =>
          v == null ? (
            <span className="ad-table-text-secondary">—</span>
          ) : (
            <span className="font-mono ad-table-mono">{v.toFixed(2)}</span>
          ),
      },
      {
        title: 'RSI',
        dataIndex: 'rsi14',
        width: 60,
        render: (v: number | null) =>
          v == null ? (
            <span className="ad-table-text-secondary">—</span>
          ) : (
            <span className="font-mono ad-table-mono">{v.toFixed(0)}</span>
          ),
      },
    ],
    [items, sectorMeta],
  );

  return (
    <div className="ad-px-4 ad-pb-4 ad-pt-2">
      {/* Filter strip */}
      <div className="ad-flex ad-flex-wrap ad-items-center ad-gap-3 ad-mb-3 sector-rotation__filter-bar">
        <div className="ad-flex ad-flex-wrap ad-items-center ad-gap-2 sector-rotation__filter-group">
          <span className="ad-table-text-secondary sector-rotation__filter-label">板块</span>
          <Select
            value={selectedSector ?? undefined}
            onChange={(v) => setSelectedSector(v)}
            className="sector-rotation__sector-select"
            placeholder={`选择${classification === 'SW' ? '申万一级' : 'GICS'}板块`}
            options={sectors.map((s) => ({
              label: `${s.sector} (${s.stock_count}股 / ${s.etf_count}基)`,
              value: s.sector,
            }))}
            showSearch
            optionFilterProp="label"
          />
        </div>
        <div className="ad-flex ad-flex-wrap ad-items-center ad-gap-2 sector-rotation__filter-group">
          <span className="ad-table-text-secondary sector-rotation__filter-label">TOP</span>
          <Select
            value={topN}
            onChange={(v) => setTopN(v)}
            className="sector-rotation__topn-select"
            options={[
              { label: '10', value: 10 },
              { label: '20', value: 20 },
              { label: '50', value: 50 },
              { label: '100', value: 100 },
              { label: '200', value: 200 },
            ]}
          />
        </div>
        {data && (
          <span className="ad-table-text-secondary sector-rotation__filter-label">
            展示 {data.count} / {data.total_in_sector} （按 {items[0]?.weight_label ?? '权重'} 降序）
            {data.trade_date ? ` · 快照 ${data.trade_date}` : ''}
          </span>
        )}
      </div>

      {isLoading && !data ? (
        <LoadingBlock size="sm" />
      ) : !selectedSector ? (
        <EmptyState
          title="请选择板块"
          description={`从上方下拉框选择要查看的${classification === 'SW' ? '申万一级' : 'GICS'}板块。`}
        />
      ) : items.length === 0 ? (
        <EmptyState
          title="暂无成份股"
          description={
            data?.total_in_sector === 0
              ? `板块 ${selectedSector} 当前没有任何 ETF/个股。`
              : `板块 ${selectedSector} 没有可显示的成份股（可能尚未刷新指标）。`
          }
        />
      ) : (
        <div className="ad-table-scroll ad-table-sticky">
          <Table
            dataSource={items.map((i) => ({ ...i, key: i.code }))}
            columns={constituentsColumns}
            rowKey="code"
            size="small"
            scroll={{ x: 'max-content' }}
            pagination={false}
            loading={isFetching && !!data}
          />
        </div>
      )}
    </div>
  );
}

/** Format a CNY 元 weight (e.g. 2_500_000_000 → "25.00亿"). */
function formatWeight(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e8) return `${(value / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(value / 1e4).toFixed(2)}万`;
  return value.toFixed(0);
}