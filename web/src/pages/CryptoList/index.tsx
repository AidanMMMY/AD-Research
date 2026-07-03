import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Input, Select, List, Skeleton } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useCryptoList } from '@/hooks/useCrypto';
import { useCryptoStore } from '@/stores/crypto';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { useDensity } from '@/hooks/useDensity';
import { useDebounce } from '@/hooks/useDebounce';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import EmptyState from '@/components/EmptyState';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import ReturnTag from '@/components/ReturnTag';
import ThemeTag from '@/components/ThemeTag';

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
  const { density } = useDensity();
  const filters = useCryptoStore();
  const [page, setPage] = useState(1);
  const pageLoadedAt = useMemo(() => new Date().toISOString(), []);
  const debouncedSearch = useDebounce(filters.search, 300);

  const { data, isLoading } = useCryptoList({
    search: debouncedSearch || undefined,
    category: filters.category,
    sort_by: filters.sortBy,
    sort_order: filters.sortOrder,
    page,
    page_size: 50,
  });

  const rowSize = density === 'dense' ? 'small' : density === 'spacious' ? 'large' : 'middle';

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
      // Prefer canonical change_pct; fall back to deprecated change_24h
      // so older API responses (or cache) keep rendering.
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
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="数字货币"
        title="加密货币"
        description="浏览和分析主流数字货币，数据来源于 Binance"
      />

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
          style={{ width: 240 }}
        />
        <Select
          placeholder="分类"
          allowClear
          style={{ width: 140 }}
          value={filters.category}
          onChange={(v) => {
            filters.setCategory(v);
            setPage(1);
          }}
          options={CATEGORIES.map((c) => ({ label: c, value: c }))}
        />
        <Select
          placeholder="排序"
          style={{ width: 120 }}
          value={filters.sortBy}
          onChange={(v) => filters.setSort(v, filters.sortOrder)}
          options={SORT_OPTIONS}
        />
        <Select
          style={{ width: 80 }}
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
            dataSource={data?.items ?? []}
            renderItem={(item: any) => (
              <List.Item
                onClick={() => navigate(`/crypto/${item.code}`)}
                className="ad-cursor-pointer"
              >
                <List.Item.Meta
                  title={<InstrumentCodeTag code={item.code} name={item.name} name_zh={item.name_zh} />}
                  description={
                    <span className="mobile-list-item__meta">
                      {item.category} · {item.exchange}
                    </span>
                  }
                />
                <div className="crypto-list-item__right">
                  <div className="tabular-nums crypto-list-item__price">
                    {item.price != null ? `$${item.price < 0.01 ? item.price.toFixed(6) : item.price < 1 ? item.price.toFixed(4) : item.price.toFixed(2)}` : '-'}
                  </div>
                  <ReturnTag value={item.change_pct ?? item.change_24h} />
                </div>
              </List.Item>
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
        <Table
          columns={columns}
          dataSource={data?.items ?? []}
          rowKey="code"
          loading={isLoading}
          size={rowSize as any}
          scroll={{ x: 'max-content' }}
          onRow={(record) => ({
            onClick: () => navigate(`/crypto/${record.code}`),
          })}
          pagination={{
            current: page,
            pageSize: 50,
            total: data?.total ?? 0,
            onChange: setPage,
            showSizeChanger: false,
          }}
          locale={{
            emptyText: (
              <EmptyState
                title="没有符合条件的币种"
                description="尝试调整上方筛选条件，或清空搜索关键词查看全部"
              />
            ),
          }}
        />
      )}
    </PageShell>
  );
}
