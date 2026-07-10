import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Empty,
  Skeleton,
  Select,
  Table,
  Tag,
} from 'antd';
import { useQuery } from '@tanstack/react-query';
import {
  instrumentApi,
  stockFundamentalApi,
  cryptoApi,
} from '@/api';
import Panel from '@/components/Panel';
import EmptyState from '@/components/EmptyState';
import { formatRelative } from '@/utils/datetime';
import './TypeAwareModules.css';
import type { ETFHoldingSnapshot } from '@/types/instrument';
import type { InstrumentInfo } from '@/types/instrument';

export interface TypeAwareModulesProps {
  /** The instrument whose type drives which module is rendered. */
  instrument: InstrumentInfo;
}

type ModuleKind = 'holdings' | 'fundamentals' | 'market-data' | 'basic-info';

/**
 * Pick the "third-slot" module for an instrument, based on its
 * ``instrument_type``.
 *
 * Extension point
 * ---------------
 * This helper is intentionally trivial so the inline-layout refactor
 * (parallel task) can simply call it and then render the matching
 * component from a flat list. Keep it pure: no JSX, no hooks.
 */
export function getInstrumentModuleKind(instrumentType?: string | null): ModuleKind {
  switch (instrumentType) {
    case 'ETF':
      return 'holdings';
    case 'STOCK':
      return 'fundamentals';
    case 'CRYPTO':
      return 'market-data';
    default:
      // Unknown type (or loading). Fall back to a light basic-info card
      // so we never render an obviously wrong module.
      return 'basic-info';
  }
}

/**
 * Snapshot date picker for the ETF holdings view. Extracted here so the
 * component owns its own data fetching and doesn't pollute the parent
 * page with state.
 */
function HoldingsSnapshotPicker({
  snapshots,
  snapshotsLoading,
  value,
  onChange,
}: {
  snapshots: ETFHoldingSnapshot[] | undefined;
  snapshotsLoading: boolean;
  value: string | null;
  onChange: (next: string | null) => void;
}) {
  const options = useMemo(() => {
    const list: { label: React.ReactNode; value: string }[] = [
      { label: '最新 (auto)', value: '__latest__' },
    ];
    if (snapshots && snapshots.length) {
      for (const s of snapshots) {
        const date = s.holdings_as_of_date;
        const relative = formatRelative(`${date}T00:00:00`);
        list.push({
          value: date,
          label: (
            <span className="type-aware-option">
              <span className="tabular-nums">{date}</span>
              <span className="ad-text-small ad-text-tertiary">
                {relative || '刚刚'}
              </span>
              <span className="ad-text-small ad-text-tertiary">
                · {s.holding_count}只
              </span>
            </span>
          ),
        });
      }
    }
    return list;
  }, [snapshots]);

  const sortedOptions = useMemo(() => {
    const [latest, ...rest] = options;
    const sortedRest = [...rest].sort((a, b) => (b.value > a.value ? 1 : -1));
    return [latest, ...sortedRest];
  }, [options]);

  return (
    <Select
      size="small"
      className="type-aware-picker"
      value={value ?? '__latest__'}
      loading={snapshotsLoading}
      disabled={snapshotsLoading && !snapshots}
      onChange={(next) => onChange(next === '__latest__' ? null : next)}
      options={sortedOptions}
      placeholder="选择报告期"
    />
  );
}

/**
 * ETF branch — top-10 holdings with snapshot picker.
 */
function EtfHoldingsModule({ instrument }: { instrument: InstrumentInfo }) {
  const navigate = useNavigate();
  const [selectedSnapshotDate, setSelectedSnapshotDate] = useState<string | null>(null);

  const { data: holdingsData, isLoading: holdingsLoading, error: holdingsError } = useQuery({
    queryKey: ['instrument-holdings', instrument.code, selectedSnapshotDate],
    queryFn: () =>
      instrumentApi
        .holdings(instrument.code, selectedSnapshotDate ? { date: selectedSnapshotDate } : undefined)
        .then((r) => r.data),
    enabled: !!instrument.code,
    retry: 1,
  });

  const { data: holdingsSnapshotsData, isLoading: snapshotsLoading } = useQuery({
    queryKey: ['instrument-holdings-snapshots', instrument.code],
    queryFn: () => instrumentApi.holdingsSnapshots(instrument.code).then((r) => r.data),
    enabled: !!instrument.code,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  return (
    <Panel
      title="前十大持仓"
      padding="md"
      extra={
        <HoldingsSnapshotPicker
          snapshots={holdingsSnapshotsData?.items}
          snapshotsLoading={snapshotsLoading}
          value={selectedSnapshotDate}
          onChange={setSelectedSnapshotDate}
        />
      }
    >
      {holdingsLoading ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : holdingsError ? (
        <Alert type="error" message="加载持仓数据失败" />
      ) : !holdingsData?.holdings?.length ? (
        <EmptyState
          title="暂无持仓数据"
          description={
            selectedSnapshotDate
              ? `该报告期 (${selectedSnapshotDate}) 暂无持仓数据`
              : '该标的暂无持仓数据'
          }
        />
      ) : (
        <div>
          <Table
            dataSource={holdingsData.holdings.map((h, idx) => ({ ...h, key: idx }))}
            pagination={false}
            size="small"
            onRow={(row) => ({
              onClick: () => navigate(`/instruments/${row.holding_code}`),
              style: { cursor: 'pointer' },
            })}
            columns={[
              { title: '股票代码', dataIndex: 'holding_code', key: 'holding_code' },
              {
                title: '股票名称',
                dataIndex: 'holding_name',
                key: 'holding_name',
                render: (v: string | null) => v ?? '—',
              },
              {
                title: '持仓权重',
                dataIndex: 'weight',
                key: 'weight',
                align: 'right',
                render: (v: number | null) => (v != null ? `${(v * 100).toFixed(2)}%` : '—'),
              },
              {
                title: '持股数',
                dataIndex: 'shares',
                key: 'shares',
                align: 'right',
                render: (v: number | null) => (v != null ? v.toLocaleString() : '—'),
              },
              {
                title: '持仓市值',
                dataIndex: 'market_value',
                key: 'market_value',
                align: 'right',
                render: (v: number | null) => (v != null ? v.toLocaleString() : '—'),
              },
              {
                title: '报告期',
                dataIndex: 'holdings_as_of_date',
                key: 'holdings_as_of_date',
                render: (v: string | null) => v ?? '—',
              },
            ]}
          />
          {holdingsData.holdings_as_of_date && (
            <div className="type-aware-footer">
              <span>报告期：{holdingsData.holdings_as_of_date}</span>
              {selectedSnapshotDate && holdingsData.holdings_as_of_date !== selectedSnapshotDate && (
                <Tag color="processing">非默认快照</Tag>
              )}
              {holdingsData.holdings_as_of_date && (
                <span className="type-aware-footer-sub">
                  ({formatRelative(`${holdingsData.holdings_as_of_date}T00:00:00`) || '刚刚'})
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

function formatFundSize(value: number, market?: string) {
  if (market === 'US') {
    if (value >= 1e12) return `${(value / 1e12).toFixed(2)}T USD`;
    if (value >= 1e9) return `${(value / 1e9).toFixed(1)}B USD`;
    return `${(value / 1e6).toFixed(1)}M USD`;
  }
  return `${(value / 1e8).toFixed(1)}亿`;
}

function formatMarketCap(value: number, market?: string) {
  if (market === 'A股') return `${(value / 1e8).toFixed(1)}亿 CNY`;
  if (value >= 1e12) return `${(value / 1e12).toFixed(2)}T USD`;
  if (value >= 1e9) return `${(value / 1e9).toFixed(1)}B USD`;
  return `${(value / 1e6).toFixed(1)}M USD`;
}

/**
 * STOCK branch — basic financial highlights with a clear placeholder
 * for fundamentals that the API doesn't yet expose on
 * ``InstrumentInfo``. We render ``market_cap`` from the instrument
 * itself when available, plus a richer valuation block from
 * ``stockFundamentalApi`` (PE / PB / EPS …) for A-share names.
 */
function StockFundamentalsModule({ instrument }: { instrument: InstrumentInfo }) {
  const { data: stockFund, isLoading: fundLoading, error: fundError } = useQuery({
    queryKey: ['stock-fundamental', instrument.code],
    queryFn: () => stockFundamentalApi.get(instrument.code).then((r) => r.data),
    enabled: !!instrument.code,
    retry: 1,
  });

  const marketCapAvailable = instrument.market_cap != null;
  const fundAvailable = !fundLoading && !fundError && stockFund != null;
  const hasAnyData = marketCapAvailable || fundAvailable;

  return (
    <Panel title="财务亮点" padding="md">
      {!hasAnyData && fundLoading ? (
        <Skeleton active paragraph={{ rows: 4 }} />
      ) : !hasAnyData ? (
        <EmptyState
          title="财务数据待接入"
          description="当前 API 尚未返回该个股的基本面数据；可稍后再来查看，或关注综合评分与近期研报获取定性判断。"
        />
      ) : (
        <div>
          <div className="valuation-grid">
            {instrument.market_cap != null
              ? [
                  {
                    title: '总市值',
                    value: instrument.market_cap,
                    suffix: instrument.market === 'A股' ? '亿 CNY' : undefined,
                    formatter: (v: number) =>
                      instrument.market === 'A股'
                        ? (v / 1e8).toFixed(1)
                        : v.toLocaleString(),
                  },
                ].map((m) => (
                  <div key={m.title} className="valuation-cell">
                    <div className="valuation-cell__label">{m.title}</div>
                    <div className="valuation-cell__value tabular-nums">
                      {m.formatter(m.value)}
                      {m.suffix && <span className="valuation-cell__suffix">{m.suffix}</span>}
                    </div>
                  </div>
                ))
              : null}
            {fundAvailable && stockFund
              ? [
                  { title: 'PE (TTM)', value: stockFund.pe_ttm, suffix: '倍', precision: 2 },
                  { title: 'PB', value: stockFund.pb, suffix: '倍', precision: 2 },
                  {
                    title: '总市值',
                    value: stockFund.total_mv ? (stockFund.total_mv / 10000).toFixed(2) : undefined,
                    suffix: '亿 CNY',
                  },
                  {
                    title: '流通市值',
                    value: stockFund.circ_mv ? (stockFund.circ_mv / 10000).toFixed(2) : undefined,
                    suffix: '亿 CNY',
                  },
                  {
                    title: '换手率（自由流通）',
                    value: stockFund.turnover_rate_f,
                    suffix: '%',
                    precision: 2,
                  },
                  { title: '量比', value: stockFund.volume_ratio, precision: 2 },
                  stockFund.eps != null
                    ? { title: 'EPS（最新财报）', value: stockFund.eps, suffix: '元', precision: 2 }
                    : null,
                  stockFund.roe != null
                    ? { title: 'ROE（最新财报）', value: stockFund.roe, suffix: '%', precision: 2 }
                    : null,
                  stockFund.revenue_yoy != null
                    ? { title: '营收 YoY', value: stockFund.revenue_yoy, suffix: '%', precision: 2 }
                    : null,
                  stockFund.grossprofit_margin != null
                    ? { title: '毛利率', value: stockFund.grossprofit_margin, suffix: '%', precision: 2 }
                    : null,
                ]
                  .filter(Boolean)
                  .map((m: any) => (
                    <div key={m.title} className="valuation-cell">
                      <div className="valuation-cell__label">{m.title}</div>
                      <div className="valuation-cell__value tabular-nums">
                        {m.value !== undefined && m.value !== null ? (
                          <>
                            {typeof m.value === 'number' && m.precision !== undefined
                              ? m.value.toFixed(m.precision)
                              : m.value}
                            {m.suffix && <span className="valuation-cell__suffix">{m.suffix}</span>}
                          </>
                        ) : (
                          <span className="valuation-cell__empty">—</span>
                        )}
                      </div>
                    </div>
                  ))
              : null}
          </div>
          <Alert
            type="info"
            message="数据来源：Tushare Pro"
            description={`估值日期：${stockFund?.trade_date || '未知'}。`}
            className="valuation-alert ad-mt-3"
          />
        </div>
      )}
    </Panel>
  );
}

/**
 * CRYPTO branch — live market data card. Pulls ``cryptoApi.get``
 * which returns price, 24h change, 24h volume and 24h high / low.
 * Market-cap and circulating-supply fields aren't yet on the
 * ``CryptoDetail`` API; the card marks them as pending so we don't
 * silently render zeros.
 */
function CryptoMarketDataModule({ instrument }: { instrument: InstrumentInfo }) {
  const { data: cryptoDetail, isLoading, error } = useQuery({
    queryKey: ['crypto-detail', instrument.code],
    queryFn: () => cryptoApi.get(instrument.code),
    enabled: !!instrument.code && instrument.instrument_type === 'CRYPTO',
    retry: 1,
  });

  if (isLoading) {
    return (
      <Panel title="市场数据" padding="md">
        <Skeleton active paragraph={{ rows: 4 }} />
      </Panel>
    );
  }
  if (error || !cryptoDetail) {
    return (
      <Panel title="市场数据" padding="md">
        <Empty
          description={
            <EmptyState
              title="市场数据获取失败"
              description="无法加载数字货币实时行情，请稍后重试"
            />
          }
        />
      </Panel>
    );
  }

  const change = cryptoDetail.change_pct ?? cryptoDetail.change_24h ?? null;
  const cells = [
    {
      title: '最新价',
      value:
        cryptoDetail.price != null
          ? `${cryptoDetail.price.toLocaleString()} ${cryptoDetail.currency || 'USDT'}`
          : undefined,
    },
    {
      title: '24h 涨跌',
      value: change != null ? `${change >= 0 ? '+' : ''}${change.toFixed(2)}%` : undefined,
      color: change != null ? (change >= 0 ? 'detail-kpi-rise' : 'detail-kpi-fall') : undefined,
    },
    {
      title: '24h 最高',
      value: cryptoDetail.high_24h != null ? cryptoDetail.high_24h.toLocaleString() : undefined,
    },
    {
      title: '24h 最低',
      value: cryptoDetail.low_24h != null ? cryptoDetail.low_24h.toLocaleString() : undefined,
    },
    {
      title: '24h 成交量',
      value: cryptoDetail.volume_24h != null ? cryptoDetail.volume_24h.toLocaleString() : undefined,
      suffix: cryptoDetail.currency || 'USDT',
    },
    {
      title: '24h 成交额',
      value:
        cryptoDetail.amount_24h != null ? cryptoDetail.amount_24h.toLocaleString() : undefined,
      suffix: 'USD',
    },
  ].filter((c) => c.value != null);

  const pendingCells = [
    { title: '流通市值', pending: true },
    { title: '总市值', pending: true },
    { title: '流通供应量', pending: true },
  ];

  return (
    <Panel
      title="市场数据"
      padding="md"
      extra={
        cryptoDetail.last_updated ? (
          <span className="ad-text-small ad-text-tertiary">
            数据更新于 {cryptoDetail.last_updated}
          </span>
        ) : null
      }
    >
      <div className="valuation-grid">
        {cells.map((c) => (
          <div key={c.title} className={`valuation-cell ${c.color ?? ''}`}>
            <div className="valuation-cell__label">{c.title}</div>
            <div className="valuation-cell__value tabular-nums">
              {c.value}
              {c.suffix && <span className="valuation-cell__suffix">{c.suffix}</span>}
            </div>
          </div>
        ))}
        {pendingCells.map((c) => (
          <div key={c.title} className="valuation-cell">
            <div className="valuation-cell__label">{c.title}</div>
            <div className="valuation-cell__value tabular-nums valuation-cell__empty">
              接入中
            </div>
          </div>
        ))}
      </div>
      <Alert
        type="info"
        message="数据来源：交易所公开行情"
        description="流通市值 / 总市值 / 流通供应量等字段待公共行情聚合层接入后展示。"
        className="ad-mt-3"
      />
    </Panel>
  );
}

/**
 * Generic fallback — render whatever descriptive fields the instrument
 * exposes. Used when ``instrument_type`` is unknown / missing so we
 * never accidentally show an ETF-specific holdings table on, say, a
 * future FUND index type.
 */
function BasicInfoModule({ instrument }: { instrument: InstrumentInfo }) {
  const rows: { title: string; value: React.ReactNode }[] = [];

  if (instrument.category) rows.push({ title: '一级分类', value: instrument.category });
  if (instrument.sub_category) rows.push({ title: '二级分类', value: instrument.sub_category });
  if (instrument.sector) rows.push({ title: '板块', value: instrument.sector });
  if (instrument.industry) rows.push({ title: '行业', value: instrument.industry });
  if (instrument.country) rows.push({ title: '国家', value: instrument.country });
  if (instrument.exchange) rows.push({ title: '交易所', value: instrument.exchange });
  if (instrument.underlying_index)
    rows.push({ title: '跟踪指数', value: instrument.underlying_index });
  if (instrument.fund_manager) rows.push({ title: '基金经理', value: instrument.fund_manager });
  if (instrument.fund_size != null) {
    rows.push({
      title: '基金规模',
      value: formatFundSize(instrument.fund_size, instrument.market),
    });
  }
  if (instrument.market_cap != null) {
    rows.push({
      title: '市值',
      value: formatMarketCap(instrument.market_cap, instrument.market),
    });
  }
  if (instrument.inception_date) rows.push({ title: '成立日期', value: instrument.inception_date });
  if (instrument.expense_ratio != null) {
    rows.push({ title: '管理费率', value: `${instrument.expense_ratio.toFixed(2)}%` });
  }

  if (rows.length === 0) {
    return (
      <Panel title="基本信息" padding="md">
        <EmptyState title="暂无基础信息" description="该标的无可展示的基础字段" />
      </Panel>
    );
  }

  return (
    <Panel title="基本信息" padding="md">
      <div className="valuation-grid">
        {rows.map((r) => (
          <div key={r.title} className="valuation-cell">
            <div className="valuation-cell__label">{r.title}</div>
            <div className="valuation-cell__value tabular-nums">{r.value}</div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

/**
 * Type-aware "third-slot" module for the instrument detail page.
 *
 * Branches on ``instrument.instrument_type``:
 *
 *   - ``ETF``   → top-10 holdings (with historical snapshot picker)
 *   - ``STOCK`` → basic financial highlights (placeholder until the
 *                  API exposes per-instrument fundamentals)
 *   - ``CRYPTO``→ market data card (price / 24h volume / 24h change)
 *
 * The component is fully self-contained — it owns its own data
 * fetching and snapshot picker state — so the parent page can drop it
 * in directly without coordinating queries. This keeps the upcoming
 * inline-layout refactor (parallel task) a search-and-replace away.
 */
export default function TypeAwareModules({ instrument }: TypeAwareModulesProps) {
  const kind = getInstrumentModuleKind(instrument.instrument_type);
  switch (kind) {
    case 'holdings':
      return <EtfHoldingsModule instrument={instrument} />;
    case 'fundamentals':
      return <StockFundamentalsModule instrument={instrument} />;
    case 'market-data':
      return <CryptoMarketDataModule instrument={instrument} />;
    case 'basic-info':
    default:
      return <BasicInfoModule instrument={instrument} />;
  }
}
