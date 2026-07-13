import './styles.css';

import { useMemo, useState, type KeyboardEvent, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Input, Select, List, Skeleton } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useCryptoList } from '@/hooks/useCrypto';
import { useCryptoStore } from '@/stores/crypto';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { useDebounce } from '@/hooks/useDebounce';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import Panel from '@/components/Panel';
import EmptyState from '@/components/EmptyState';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import ReturnTag from '@/components/ReturnTag';
import ThemeTag from '@/components/ThemeTag';

/**
 * Apple-style motion layer (scoped to this page):
 * - Response: feedback lands on pointer-down (:active, 0ms), release springs back.
 * - Springs: critically-damped-ish cubic-bezier; transform-only for frame smoothness.
 * - Typography: size-specific tracking (large tight, small loose).
 * - Reduced motion: cross-fade only, transforms disabled.
 */
const ADX_STYLE = `
.adx-crypto-list {
  /* Critically-damped monotonic curve: y2 ≤ 1, no overshoot. */
  --adx-spring: cubic-bezier(0.32, 0.72, 0, 1);
  --adx-ease-out: cubic-bezier(0.22, 0.9, 0.3, 1);
}
.adx-crypto-list .ant-btn,
.adx-crypto-list .mobile-list-item {
  touch-action: manipulation;
  transition: transform 240ms var(--adx-spring), background-color 140ms var(--adx-ease-out);
}
.adx-crypto-list .ant-btn:active,
.adx-crypto-list .mobile-list-item:active {
  transform: scale(0.97);
  background-color: var(--bg-active);
  transition-duration: 0ms;
}
.adx-crypto-list .ant-table-tbody > tr {
  touch-action: manipulation;
  transition: background-color 140ms var(--adx-ease-out);
}
.adx-crypto-list .ant-table-tbody > tr:active {
  background-color: var(--bg-active);
  transition-duration: 0ms;
}
/* Heading typography: keep inverse leading, but skip the negative
   tracking that would compress CJK glyphs (zh/ja/ko). Negative tracking
   is only meaningful for Latin/numeric runs; headings here are mixed
   CJK so we drop it and rely on inverse leading alone. */
.adx-crypto-list h1,
.adx-crypto-list h2,
.adx-crypto-list .ant-typography h1,
.adx-crypto-list .ant-typography h2 {
  line-height: 1.18;
  letter-spacing: normal;
}
.adx-crypto-list .ad-text-xs,
.adx-crypto-list .ad-text-small {
  letter-spacing: 0.01em;
}
@media (prefers-reduced-motion: reduce) {
  .adx-crypto-list *,
  .adx-crypto-list *::before,
  .adx-crypto-list *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }
  .adx-crypto-list .ant-btn:active,
  .adx-crypto-list .mobile-list-item:active {
    transform: none;
  }
}
`;

function AdxShell({ children }: { children: ReactNode }) {
  return (
    <div className="adx-crypto-list">
      <style>{ADX_STYLE}</style>
      {children}
    </div>
  );
}

const CATEGORIES = [
  'Layer1', 'L2', 'DeFi', 'Exchange', 'Payments',
  'Oracle', 'Storage', 'Meme',
];

const SORT_OPTIONS = [
  { label: '名称', value: 'name' },
  { label: '价格', value: 'price' },
  { label: '24h 涨跌', value: 'change_24h' },
];

function formatUtc(iso: string): string {
  try {
    return new Date(iso).toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
  } catch {
    return iso;
  }
}

export default function CryptoList() {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const filters = useCryptoStore();
  const [page, setPage] = useState(1);
  const pageLoadedAt = useMemo(() => new Date().toISOString(), []);
  // Shorter debounce: 150ms is below the "feels laggy" threshold while
  // still coalescing burst keystrokes into one network request.
  const debouncedSearch = useDebounce(filters.search, 150);

  const { data, isLoading } = useCryptoList({
    search: debouncedSearch || undefined,
    category: filters.category,
    sort_by: filters.sortBy,
    sort_order: filters.sortOrder,
    page,
    page_size: 50,
  });

  // Client-side optimistic filter: when the user types faster than the
  // debounced fetch returns, hide rows that obviously don't match so the
  // UI reacts within the same frame as the keystroke.
  const visibleItems = useMemo(() => {
    const items = data?.items ?? [];
    const live = filters.search.trim();
    if (!live || live === debouncedSearch) return items;
    const needle = live.toUpperCase();
    return items.filter(
      (it) =>
        it.code?.toUpperCase().includes(needle) ||
        it.name?.toUpperCase().includes(needle) ||
        it.name_zh?.includes(live),
    );
  }, [data?.items, filters.search, debouncedSearch]);

  const tableWrapClass = 'ad-table-scroll ad-table-sticky';

  // The API enriches every row with the same last_updated timestamp.
  const backendTimestamp = data?.items?.[0]?.last_updated;
  const priceUpdatedAt = backendTimestamp ?? pageLoadedAt;
  const timestampLabel = backendTimestamp ? '价格更新于' : '页面加载于';

  const columns = [
    {
      title: '代币',
      render: (_: unknown, record: any) => (
        <InstrumentCodeTag code={record.code} name={record.name} name_zh={record.name_zh} />
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      render: (v: string) => v ? <ThemeTag>{v}</ThemeTag> : '-',
    },
    {
      title: '价格 (USDT)',
      dataIndex: 'price',
      width: 140,
      render: (v: number) =>
        v != null ? (
          <span className="tabular-nums mobile-list-item__value">
            {v < 0.01 ? v.toFixed(6) : v < 1 ? v.toFixed(4) : v.toFixed(2)}
          </span>
        ) : (
          '-'
        ),
    },
    {
      title: '24h 涨跌',
      dataIndex: 'change_pct',
      width: 120,
      render: (_: unknown, record: any) => (
        <ReturnTag
          value={record.change_pct ?? record.change_24h}
        />
      ),
    },
    {
      title: '24h 成交量',
      dataIndex: 'volume_24h',
      width: 140,
      render: (v: number) =>
        v != null ? (
          <span className="tabular-nums mobile-list-item__meta font-mono">
            {v >= 1e9
              ? `${(v / 1e9).toFixed(1)}B`
              : v >= 1e6
                ? `${(v / 1e6).toFixed(1)}M`
                : v >= 1e3
                  ? `${(v / 1e3).toFixed(1)}K`
                  : v.toFixed(0)}
          </span>
        ) : (
          '-'
        ),
    },
    {
      title: '交易所',
      dataIndex: 'exchange',
      width: 90,
      render: (v: string) => (
        <span className="tabular-nums mobile-list-item__meta font-mono">
          {v || '-'}
        </span>
      ),
    },
  ];

  return (
    <AdxShell>
      <PageShell maxWidth="wide">
        <PageHeader
          eyebrow="数字货币"
          title="加密货币"
          description="浏览和分析主流数字货币，数据来源于 Binance"
        />

      <Panel variant="default" padding="md">
        <FilterToolbar total={`共 ${data?.total ?? 0} 只`}>
          <Input
            placeholder="搜索币种代码或名称"
            allowClear
            prefix={<SearchOutlined className="ad-icon-tertiary" />}
            value={filters.search}
            onChange={(e) => {
              filters.setSearch(e.target.value);
              setPage(1);
            }}
            className="ad-w-full"
          />
          <Select
            placeholder="分类"
            allowClear
            className="ad-w-full"
            value={filters.category}
            onChange={(v) => {
              filters.setCategory(v);
              setPage(1);
            }}
            options={CATEGORIES.map((c) => ({ label: c, value: c }))}
          />
          <Select
            placeholder="排序"
            className="ad-w-full"
            value={filters.sortBy}
            onChange={(v) => filters.setSort(v, filters.sortOrder)}
            options={SORT_OPTIONS}
          />
          <Select
            className="ad-w-full"
            value={filters.sortOrder}
            onChange={(v) => filters.setSort(filters.sortBy, v)}
            options={[
              { label: '升序', value: 'asc' },
              { label: '降序', value: 'desc' },
            ]}
          />
        </FilterToolbar>

        <div className="ad-text-tertiary ad-text-xs ad-mb-3 ad-text-center">
          <div>
            {timestampLabel} {formatUtc(priceUpdatedAt)}
            {!backendTimestamp && '（数据来自 Binance）'}
          </div>
          <div>24h 涨跌 = (当前价 - 24小时前价格) / 24小时前价格</div>
        </div>

        {isMobile ? (
          isLoading ? (
            <Skeleton active paragraph={{ rows: 6 }} />
          ) : (data?.items?.length ?? 0) === 0 ? (
            <EmptyState
              title="没有符合条件的币种"
              description="尝试调整上方筛选条件，或清空搜索关键词查看全部"
            />
          ) : (
            <List
              className="ad-list-compact"
              dataSource={visibleItems}
              renderItem={(item: any) => (
                <div
                  role="button"
                  tabIndex={0}
                  aria-label={`查看 ${item.name ?? item.code} 详情`}
                  onClick={() => navigate(`/crypto/${item.code}`)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      navigate(`/crypto/${item.code}`);
                    }
                  }}
                  className="mobile-list-item"
                >
                  <div className="mobile-list-item__row">
                    <div className="mobile-list-item__main">
                      <InstrumentCodeTag code={item.code} name={item.name} name_zh={item.name_zh} />
                    </div>
                    <div className="mobile-list-item__metrics">
                      <span className="tabular-nums mobile-list-item__value">
                        {item.price != null ? `$${item.price < 0.01 ? item.price.toFixed(6) : item.price < 1 ? item.price.toFixed(4) : item.price.toFixed(2)}` : '-'}
                      </span>
                      <ReturnTag value={item.change_pct ?? item.change_24h} />
                    </div>
                  </div>
                  <div className="mobile-list-item__tags">
                    {item.category && <ThemeTag>{item.category}</ThemeTag>}
                    {item.exchange && <ThemeTag>{item.exchange}</ThemeTag>}
                  </div>
                </div>
              )}
              pagination={{
                current: page,
                pageSize: 50,
                total: data?.total ?? 0,
                onChange: setPage,
                size: 'small',
                className: 'mobile-list-pagination',
              }}
            />
          )
        ) : (
          <div className={tableWrapClass}>
            <Table
              columns={columns}
              dataSource={visibleItems}
              rowKey="code"
              loading={isLoading}
              size="small"
              scroll={{ x: 'max-content' }}
              onRow={(record) => ({
                onClick: () => navigate(`/crypto/${record.code}`),
                onKeyDown: (e: KeyboardEvent<HTMLTableRowElement>) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    navigate(`/crypto/${record.code}`);
                  }
                },
                tabIndex: 0,
                'aria-label': `查看 ${record.name ?? record.code} 详情`,
              })}
              pagination={{
                current: page,
                pageSize: 50,
                total: data?.total ?? 0,
                onChange: setPage,
                showSizeChanger: true,
              }}
              locale={{
                emptyText: <EmptyState title="暂无数据" />,
              }}
            />
          </div>
        )}
      </Panel>
      </PageShell>
    </AdxShell>
  );
}
