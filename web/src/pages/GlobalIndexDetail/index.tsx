/**
 * GlobalIndexDetail — 全球速览指数详情页（/global/:code）。
 *
 * 数据契约：GET /macro/indicators/{code}/detail（见 types/macro.ts 的
 * MacroIndicatorDetail）。has_ohlc=true → 蜡烛图（KLineChart）；
 * has_ohlc=false → 折线/面积图（MacroLineChart）。
 *
 * 设计语言：去卡片化（hairline + 排版优先），复用 PageShell / PageHeader /
 * Panel 与共享 .kpi-strip/.kpi-cell（列数走 --kpi-cols，本页 5 列）。
 */

import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import './styles.css';
import { Button, Radio, Tag, Typography } from 'antd';
import {
  ArrowLeftOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  MinusOutlined,
} from '@ant-design/icons';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import EmptyState from '@/components/EmptyState';
import LoadingBlock from '@/components/LoadingBlock';
import ReturnTagPct from '@/components/ReturnTagPct';
import KLineChart from '@/components/KLineChart';
import MacroLineChart from '@/components/MacroLineChart';
import { useMacroIndicatorDetail } from '@/api/macro';
import type { MacroCategory } from '@/types/macro';
import {
  formatBp,
  formatMacroValue,
  ohlcBarsToOHLCV,
  type MacroRangeKey,
} from '@/utils/macroDetail';

const { Text } = Typography;

/** 类目 key → 中文名（与速览页 CATEGORY_LABELS 口径一致）。 */
const CATEGORY_LABELS: Record<MacroCategory, string> = {
  rate: '美债利率',
  fx: '外汇',
  commodity: '大宗商品',
  index: '主要指数',
  vol: '情绪·波动',
};

/** 蜡烛图序列的时间范围（默认 6月）。 */
const OHLC_RANGE_OPTIONS: Array<{ label: string; value: MacroRangeKey }> = [
  { label: '1月', value: '1M' },
  { label: '3月', value: '3M' },
  { label: '6月', value: '6M' },
  { label: '1年', value: '1Y' },
  { label: '3年', value: '3Y' },
  { label: '5年', value: '5Y' },
  { label: '全部', value: 'ALL' },
];

/** 折线图序列的时间范围（默认 3月）。 */
const LINE_RANGE_OPTIONS: Array<{ label: string; value: MacroRangeKey }> = [
  { label: '1月', value: '1M' },
  { label: '3月', value: '3M' },
  { label: '6月', value: '6M' },
  { label: '1年', value: '1Y' },
  { label: '全部', value: 'ALL' },
];

/**
 * 基点涨跌标签（rate 类目专用）。
 * 与速览页 BpTag 同一实现：复用全局 return-tag 类（红涨绿跌随
 * data-color-convention 自动切换），数字走 formatBp 纯函数。
 */
function BpTag({ value }: { value: number }) {
  const bp = value * 100; // 百分点 → bp
  const cls = bp > 0 ? 'return-tag--rise' : bp < 0 ? 'return-tag--fall' : 'return-tag--flat';
  return (
    <span className={`return-tag tabular-nums ${cls}`}>
      {bp > 0 ? (
        <ArrowUpOutlined className="return-tag__arrow" aria-label="up" />
      ) : bp < 0 ? (
        <ArrowDownOutlined className="return-tag__arrow" aria-label="down" />
      ) : (
        <MinusOutlined className="return-tag__arrow" aria-label="flat" />
      )}
      {formatBp(value)}
    </span>
  );
}

/** KPI 单元格：小字 label + 等宽数字 value（hairline 分隔由 .kpi-cell 提供）。 */
function KpiCell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="kpi-cell">
      <div className="gid-kpi__label">{label}</div>
      <div className="gid-kpi__value">{children}</div>
    </div>
  );
}

export default function GlobalIndexDetail() {
  const { code } = useParams<{ code: string }>();
  const navigate = useNavigate();

  /* 时间范围：null = 用户未手动选择，按图表形态取默认（蜡烛 6月 / 折线 3月）。
     数据未返回前按蜡烛默认 '6M' 请求；line 序列到达后自动落到 '3M' 并重取。 */
  const [rangeOverride, setRangeOverride] = useState<MacroRangeKey | null>(null);

  /* 首次请求需要一个确定的范围 key；detail 返回后若实际形态是折线，
     effectiveRange 切换到折线默认 '3M'，React Query 按新 key 自动重取。
     提示要"粘住"（只写一次）：重取期间 detail 会短暂变回 undefined，
     若从 detail 实时推导默认值会在 6M/3M 之间来回翻转造成循环请求。 */
  const [hasOhlcHint, setHasOhlcHint] = useState<boolean | null>(null);

  const effectiveRange: MacroRangeKey =
    rangeOverride ?? (hasOhlcHint === false ? '3M' : '6M');

  const { data: detail, isLoading, error } = useMacroIndicatorDetail(code, effectiveRange);

  // detail 首次到达后同步 has_ohlc 提示（只写一次）
  useEffect(() => {
    if (detail && hasOhlcHint === null) {
      setHasOhlcHint(detail.has_ohlc);
    }
  }, [detail, hasOhlcHint]);

  const hasOhlc = detail?.has_ohlc ?? hasOhlcHint ?? true;
  const rangeOptions = hasOhlc ? OHLC_RANGE_OPTIONS : LINE_RANGE_OPTIONS;

  // OHLC bars → KLineChart OHLCV（open null 用 close 补齐，见 utils/macroDetail）
  const klineData = useMemo(
    () => (detail?.ohlc ? ohlcBarsToOHLCV(detail.ohlc) : []),
    [detail?.ohlc],
  );

  const isEmpty =
    !!detail &&
    (detail.has_ohlc ? klineData.length === 0 : (detail.points ?? []).length === 0);

  // ── 加载中 ──
  if (isLoading) {
    return (
      <PageShell maxWidth="wide">
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/global')}
          className="ad-mb-3"
        >
          返回全球速览
        </Button>
        <LoadingBlock size="lg" label="加载中…" />
      </PageShell>
    );
  }

  // ── 404 / 加载失败 / 无数据 ──
  if (error || !detail || isEmpty) {
    const status = (error as any)?.response?.status;
    return (
      <PageShell maxWidth="wide">
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/global')}
          className="ad-mb-3"
        >
          返回全球速览
        </Button>
        <Panel>
          <EmptyState
            title={status === 404 ? '该指标暂无数据' : '加载指数详情失败'}
            description={
              status === 404
                ? `代码 ${code} 尚未采集到任何数据，可能未接入或数据源暂时不可用。`
                : '请稍后重试，或返回全球速览查看其它指标。'
            }
            action={
              <Button type="primary" onClick={() => navigate('/global')}>
                返回全球速览
              </Button>
            }
          />
        </Panel>
      </PageShell>
    );
  }

  const { latest, stats, unit, source, category } = detail;
  const categoryLabel = CATEGORY_LABELS[category] ?? category;

  return (
    <PageShell maxWidth="wide" className="global-index-detail">
      <Button
        type="text"
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/global')}
        className="ad-mb-3"
      >
        返回全球速览
      </Button>

      <PageHeader
        eyebrow="全球市场速览"
        title={detail.name_zh || detail.code}
        description={
          <span className="gid-meta">
            <Tag className="gid-meta__code">{detail.code}</Tag>
            <Text type="secondary">
              {categoryLabel}
              {unit ? ` · 单位：${unit}` : ''}
              {source ? ` · 来源：${source}` : ''}
            </Text>
          </span>
        }
        extra={
          stats.last_period ? (
            <Text type="secondary" className="gid-asof">
              数据日期 {stats.last_period}
            </Text>
          ) : undefined
        }
      />

      {/* KPI strip：5 列（移动端共享类自动回落 2 列） */}
      <div className="kpi-strip gid-kpi-strip">
        <KpiCell label="最新值">
          {latest ? formatMacroValue(latest.value, unit) : '—'}
        </KpiCell>
        <KpiCell label="日涨跌">
          {category === 'rate' ? (
            latest?.change_abs != null ? (
              <BpTag value={latest.change_abs} />
            ) : (
              '—'
            )
          ) : (
            <ReturnTagPct value={latest?.change_pct} />
          )}
        </KpiCell>
        <KpiCell label="52 周最高">{formatMacroValue(stats.high_52w, unit)}</KpiCell>
        <KpiCell label="52 周最低">{formatMacroValue(stats.low_52w, unit)}</KpiCell>
        <KpiCell label="数据起始">{stats.first_period ?? '—'}</KpiCell>
      </div>

      {/* 主图 Panel：右上时间范围 + 蜡烛/折线 */}
      <Panel
        title="历史走势"
        padding="md"
        extra={
          <div className="gid-range-scroll">
            <Radio.Group
              value={effectiveRange}
              onChange={(e) => setRangeOverride(e.target.value as MacroRangeKey)}
              optionType="button"
              buttonStyle="solid"
              size="small"
            >
              {rangeOptions.map((opt) => (
                <Radio.Button key={opt.value} value={opt.value}>
                  {opt.label}
                </Radio.Button>
              ))}
            </Radio.Group>
          </div>
        }
      >
        {detail.has_ohlc ? (
          <KLineChart
            data={klineData}
            overlays={{ ma5: true, ma20: true }}
            adjusted={false}
          />
        ) : (
          <MacroLineChart points={detail.points ?? []} unit={unit} />
        )}
      </Panel>
    </PageShell>
  );
}
