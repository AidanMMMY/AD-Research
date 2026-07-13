import { useMemo, useState, type ReactNode } from 'react';
import './styles.css';
import {
  Table, Input, Select, Button, Space, Tag, Skeleton, message, Statistic, Card, Tabs,
} from 'antd';
import { ReloadOutlined, SearchOutlined, FundOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import FilterToolbar from '@/components/FilterToolbar';
import EmptyState from '@/components/EmptyState';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import LastUpdated from '@/components/LastUpdated';
import ThemeTag from '@/components/ThemeTag';
import { NULL_PLACEHOLDER } from '@/utils/format';
import { useDebounce } from '@/hooks/useDebounce';
import {
  useMicrostructureLhb,
  useMicrostructureHsgt,
  useMicrostructureMargin,
  useMicrostructureReleases,
  useMicrostructureSummary,
  useRefreshMicrostructure,
} from '@/api/microstructure';
import type {
  LhbRecord,
  HsgtFlow,
  MarginBalance,
  RestrictedRelease,
} from '@/api/microstructure';

/**
 * Apple-style motion layer (scoped to this page):
 * - Response: feedback lands on pointer-down (:active, 0ms), release springs back.
 * - Springs: critically-damped-ish cubic-bezier; transform-only for frame smoothness.
 * - Typography: size-specific tracking (large tight, small loose).
 * - Reduced motion: cross-fade only, transforms disabled.
 */
const ADX_STYLE = `
.adx-microstructure {
  /* Critically-damped monotonic curve: y2 ≤ 1, no overshoot. */
  --adx-spring: cubic-bezier(0.32, 0.72, 0, 1);
  --adx-ease-out: cubic-bezier(0.22, 0.9, 0.3, 1);
}
.adx-microstructure .ant-btn {
  touch-action: manipulation;
  transition: transform 240ms var(--adx-spring), background-color 140ms var(--adx-ease-out);
}
.adx-microstructure .ant-btn:active {
  transform: scale(0.97);
  transition-duration: 0ms;
}
.adx-microstructure .ant-tabs-tab {
  touch-action: manipulation;
  transition: color 140ms var(--adx-ease-out);
}
.adx-microstructure .ant-table-tbody > tr {
  transition: background-color 140ms var(--adx-ease-out);
}
.adx-microstructure h1,
.adx-microstructure h2,
.adx-microstructure .ant-typography h1,
.adx-microstructure .ant-typography h2 {
  letter-spacing: -0.02em;
  line-height: 1.18;
}
.adx-microstructure .ad-text-xs,
.adx-microstructure .ad-text-small {
  letter-spacing: 0.01em;
}
@media (prefers-reduced-motion: reduce) {
  .adx-microstructure *,
  .adx-microstructure *::before,
  .adx-microstructure *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }
  .adx-microstructure .ant-btn:active {
    transform: none;
  }
}
`;

function AdxShell({ children }: { children: ReactNode }) {
  return (
    <div className="adx-microstructure">
      <style>{ADX_STYLE}</style>
      {children}
    </div>
  );
}

function formatMoney(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return NULL_PLACEHOLDER;
  if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(digits)} 亿`;
  if (Math.abs(v) >= 1e4) return `${(v / 1e4).toFixed(digits)} 万`;
  return v.toFixed(digits);
}

function formatPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return NULL_PLACEHOLDER;
  return `${v.toFixed(2)}%`;
}

export default function MicrostructurePage() {
  const [tab, setTab] = useState('lhb');

  // Filters
  const [ticker, setTicker] = useState<string | undefined>();
  const [lhbPage, setLhbPage] = useState(1);
  const [marginExchange, setMarginExchange] = useState<string | undefined>();
  const [releasePage, setReleasePage] = useState(1);

  // Debounce the ticker so each keystroke does not fan out into 3 parallel
  // network requests (lhb / margin / release share the same ts_code param).
  // 250 ms is below the "feels laggy" threshold while still coalescing
  // burst typing into a single fetch cycle.
  const debouncedTicker = useDebounce(ticker, 250);

  const lhbParams = useMemo(
    () => ({ page: lhbPage, page_size: 20, ts_code: debouncedTicker }),
    [lhbPage, debouncedTicker],
  );
  const marginParams = useMemo(
    () => ({ page: 1, page_size: 20, ts_code: debouncedTicker, exchange: marginExchange }),
    [debouncedTicker, marginExchange],
  );
  const releaseParams = useMemo(
    () => ({ page: releasePage, page_size: 20, ts_code: debouncedTicker }),
    [releasePage, debouncedTicker],
  );

  const { data: summary, dataUpdatedAt } = useMicrostructureSummary();
  const { data: lhbData, isLoading: lhbLoading } = useMicrostructureLhb(lhbParams);
  const { data: hsgtData, isLoading: hsgtLoading } = useMicrostructureHsgt({ days: 30 });
  const { data: marginData, isLoading: marginLoading } = useMicrostructureMargin(marginParams);
  const { data: releaseData, isLoading: releaseLoading } = useMicrostructureReleases(releaseParams);
  const refreshMutation = useRefreshMicrostructure();

  const handleRefresh = async () => {
    try {
      const res = await refreshMutation.mutateAsync();
      message.success(`微结构数据刷新完成: ${res.records} 条`);
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(`刷新失败: ${detail ?? '未知错误'}`);
    }
  };

  const lhbColumns: ColumnsType<LhbRecord> = [
    { title: '日期', dataIndex: 'trade_date', key: 'trade_date', width: 110 },
    { title: '代码', dataIndex: 'ts_code', key: 'ts_code', width: 110, render: (v: string) => <ThemeTag variant="accent">{v}</ThemeTag> },
    { title: '名称', dataIndex: 'name', key: 'name', width: 100, ellipsis: true },
    { title: '涨跌幅', dataIndex: 'pct_change', key: 'pct_change', width: 90, className: 'tabular-nums', render: formatPct },
    { title: '净买额', dataIndex: 'lhb_net_amount', key: 'lhb_net_amount', width: 120, className: 'tabular-nums', render: (v: number | null) => formatMoney(v) },
    { title: '原因', dataIndex: 'reason', key: 'reason', ellipsis: true },
  ];

  const hsgtColumns: ColumnsType<HsgtFlow> = [
    { title: '日期', dataIndex: 'trade_date', key: 'trade_date', width: 110 },
    { title: '类型', dataIndex: 'type', key: 'type', width: 90, render: (v: string) => <Tag>{v}</Tag> },
    { title: '净流入', dataIndex: 'net_amount', key: 'net_amount', width: 120, className: 'tabular-nums', render: (v: number | null) => formatMoney(v) },
    { title: '当日余额', dataIndex: 'balance', key: 'balance', width: 120, className: 'tabular-nums', render: (v: number | null) => formatMoney(v) },
  ];

  const marginColumns: ColumnsType<MarginBalance> = [
    { title: '日期', dataIndex: 'trade_date', key: 'trade_date', width: 110 },
    { title: '代码', dataIndex: 'ts_code', key: 'ts_code', width: 110, render: (v: string) => <ThemeTag variant="accent">{v}</ThemeTag> },
    { title: '名称', dataIndex: 'name', key: 'name', width: 100, ellipsis: true },
    { title: '交易所', dataIndex: 'exchange', key: 'exchange', width: 80, render: (v: string) => <Tag>{v}</Tag> },
    { title: '融资余额', dataIndex: 'financing_balance', key: 'financing_balance', width: 120, className: 'tabular-nums', render: (v: number | null) => formatMoney(v) },
    { title: '融券余额', dataIndex: 'securities_balance', key: 'securities_balance', width: 120, className: 'tabular-nums', render: (v: number | null) => formatMoney(v) },
  ];

  const releaseColumns: ColumnsType<RestrictedRelease> = [
    { title: '解禁日', dataIndex: 'restricted_date', key: 'restricted_date', width: 120 },
    { title: '代码', dataIndex: 'ts_code', key: 'ts_code', width: 110, render: (v: string) => <ThemeTag variant="accent">{v}</ThemeTag> },
    { title: '名称', dataIndex: 'name', key: 'name', width: 100, ellipsis: true },
    { title: '类型', dataIndex: 'restricted_type', key: 'restricted_type', width: 90 },
    { title: '解禁数量', dataIndex: 'restricted_number', key: 'restricted_number', width: 120, className: 'tabular-nums', render: (v: number | null) => v?.toLocaleString() ?? NULL_PLACEHOLDER },
    { title: '解禁市值', dataIndex: 'restricted_amount', key: 'restricted_amount', width: 120, className: 'tabular-nums', render: (v: number | null) => formatMoney(v) },
    { title: '占比 %', dataIndex: 'lift_ratio', key: 'lift_ratio', width: 90, className: 'tabular-nums', render: formatPct },
  ];

  const totalCount = useMemo(
    () =>
      (lhbData?.total ?? 0) +
      (hsgtData?.items.length ?? 0) +
      (marginData?.items.length ?? 0) +
      (releaseData?.total ?? 0),
    [lhbData, hsgtData, marginData, releaseData],
  );

  return (
    <AdxShell>
      <PageShell maxWidth="wide">
        <PageHeader
          title="微结构数据"
        description="A 股龙虎榜 / 沪深港通 / 融资融券 / 限售解禁 4 类微结构信号。每交易日 18:30 Asia/Shanghai 自动刷新。"
        extra={
          <Space>
            <LastUpdated at={dataUpdatedAt} />
            <Button
              type="primary"
              icon={<ReloadOutlined />}
              loading={refreshMutation.isPending}
              onClick={handleRefresh}
            >
              全量刷新
            </Button>
          </Space>
        }
      />

      <ResponsiveGrid cols={4} gap="md" className="ad-mb-5">
        <Card>
          <Statistic
            title="最新龙虎榜条数"
            value={summary?.lhb?.count ?? 0}
            prefix={<FundOutlined />}
            suffix={summary?.lhb?.trade_date ? ` (${summary.lhb.trade_date})` : ''}
          />
        </Card>
        <Card>
          <Statistic
            title="北向净流入"
            value={summary?.hsgt?.north_net ?? 0}
            precision={0}
            className={(summary?.hsgt?.north_net ?? 0) >= 0 ? 'micro-kpi-rise' : 'micro-kpi-fall'}
            suffix="元"
          />
        </Card>
        <Card>
          <Statistic
            title="融资余额合计"
            value={summary?.margin?.total_financing_balance ?? 0}
            precision={0}
            suffix="元"
          />
        </Card>
        <Card>
          <Statistic
            title="30 日内解禁"
            value={summary?.release?.upcoming_30d_count ?? 0}
            suffix="次"
          />
        </Card>
      </ResponsiveGrid>

      <FilterToolbar total={`共 ${totalCount} 条`} className="ad-mb-5">
        <Input
          placeholder="证券代码 (000001.SZ)"
          value={ticker ?? ''}
          onChange={(e) => setTicker(e.target.value.toUpperCase() || undefined)}
          className="ad-input--md"
          prefix={<SearchOutlined />}
          allowClear
        />
        <Select
          placeholder="交易所"
          value={marginExchange}
          onChange={(v) => setMarginExchange(v)}
          allowClear
          disabled={tab !== 'margin'}
          className="ad-select--xxs"
          options={[
            { value: 'SSE', label: 'SSE 上交所' },
            { value: 'SZSE', label: 'SZSE 深交所' },
          ]}
        />
      </FilterToolbar>

      <Panel title="明细列表">
        <Tabs
          activeKey={tab}
          onChange={setTab}
          items={[
            {
              key: 'lhb',
              label: (
                <span className="microstructure__tab-label">
                  龙虎榜
                  <span className="microstructure__tab-badge">{lhbData?.total ?? 0}</span>
                </span>
              ),
              children: lhbLoading ? (
                <Skeleton active />
              ) : !lhbData || lhbData.items.length === 0 ? (
                <EmptyState title="暂无龙虎榜数据" />
              ) : (
                <div className="ad-table-scroll ad-table-sticky ad-scroll-hint">
                  <Table
                    rowKey="id"
                    dataSource={lhbData.items}
                    columns={lhbColumns}
                    size="small"
                    scroll={{ x: 'max-content' }}
                    pagination={{
                      current: lhbPage,
                      pageSize: 20,
                      total: lhbData.total,
                      onChange: setLhbPage,
                    }}
                  />
                </div>
              ),
            },
            {
              key: 'hsgt',
              label: (
                <span className="microstructure__tab-label">
                  沪深港通
                  <span className="microstructure__tab-badge">{hsgtData?.items.length ?? 0}</span>
                </span>
              ),
              children: hsgtLoading ? (
                <Skeleton active />
              ) : !hsgtData || hsgtData.items.length === 0 ? (
                <EmptyState title="暂无沪深港通数据" />
              ) : (
                <div className="ad-table-scroll ad-table-sticky ad-scroll-hint">
                  <Table
                    rowKey="id"
                    dataSource={hsgtData.items}
                    columns={hsgtColumns}
                    size="small"
                    scroll={{ x: 'max-content' }}
                    pagination={false}
                  />
                </div>
              ),
            },
            {
              key: 'margin',
              label: (
                <span className="microstructure__tab-label">
                  融资融券
                  <span className="microstructure__tab-badge">{marginData?.items.length ?? 0}</span>
                </span>
              ),
              children: marginLoading ? (
                <Skeleton active />
              ) : !marginData || marginData.items.length === 0 ? (
                <EmptyState title="暂无融资融券数据" />
              ) : (
                <div className="ad-table-scroll ad-table-sticky ad-scroll-hint">
                  <Table
                    rowKey="id"
                    dataSource={marginData.items}
                    columns={marginColumns}
                    size="small"
                    scroll={{ x: 'max-content' }}
                    pagination={false}
                  />
                </div>
              ),
            },
            {
              key: 'releases',
              label: (
                <span className="microstructure__tab-label">
                  限售解禁
                  <span className="microstructure__tab-badge">{releaseData?.total ?? 0}</span>
                </span>
              ),
              children: releaseLoading ? (
                <Skeleton active />
              ) : !releaseData || releaseData.items.length === 0 ? (
                <EmptyState title="暂无限售解禁数据" />
              ) : (
                <div className="ad-table-scroll ad-table-sticky ad-scroll-hint">
                  <Table
                    rowKey="id"
                    dataSource={releaseData.items}
                    columns={releaseColumns}
                    size="small"
                    scroll={{ x: 'max-content' }}
                    pagination={{
                      current: releasePage,
                      pageSize: 20,
                      total: releaseData.total,
                      onChange: setReleasePage,
                    }}
                  />
                </div>
              ),
            },
          ]}
        />
      </Panel>
      </PageShell>
    </AdxShell>
  );
}
