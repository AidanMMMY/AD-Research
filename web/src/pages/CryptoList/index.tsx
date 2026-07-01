import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Input, Select, List, Skeleton } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useCryptoList } from '@/hooks/useCrypto';
import { useCryptoStore } from '@/stores/crypto';
import { useIsMobile } from '@/hooks/useBreakpoint';
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

export default function CryptoList() {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const filters = useCryptoStore();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useCryptoList({
    search: filters.search || undefined,
    category: filters.category,
    sort_by: filters.sortBy,
    sort_order: filters.sortOrder,
    page,
    page_size: 50,
  });

  const columns = [
    {
      title: '代币',
      render: (_: unknown, record: any) => (
        <InstrumentCodeTag code={record.code} name={record.name} />
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
          <span
            style={{
              fontSize: 'var(--text-body-size)',
              fontWeight: 600,
              color: 'var(--text-secondary)',
              fontFamily: 'var(--font-mono)',
            }}
          >
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
          <span
            style={{
              fontSize: 'var(--text-small-size)',
              color: 'var(--text-tertiary)',
              fontFamily: 'var(--font-mono)',
            }}
          >
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
        <span
          style={{
            fontSize: 'var(--text-small-size)',
            color: 'var(--text-tertiary)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          {v || '-'}
        </span>
      ),
    },
  ];

  return (
    <div>
      <h1
        style={{
          fontSize: 'var(--text-h1-size)',
          fontWeight: 500,
          color: 'var(--text-primary)',
          margin: '0 0 8px',
          letterSpacing: '-0.03em',
        }}
      >
        加密货币
      </h1>
      <p
        style={{
          margin: '0 0 32px',
          color: 'var(--text-tertiary)',
          fontSize: 'var(--text-body-size)',
        }}
      >
        浏览和分析主流数字货币，数据来源于 Binance
      </p>

      {/* Filters */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: 'var(--space-3)',
          paddingBottom: 'var(--space-4)',
          borderBottom: '1px solid var(--border-default)',
          marginBottom: 'var(--space-5)',
        }}
      >
        <Input
          placeholder="搜索币种代码或名称"
          allowClear
          prefix={<SearchOutlined style={{ color: 'var(--text-tertiary)' }} />}
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
      </div>

      {/* Content */}
      {isMobile ? (
        isLoading ? (
          <Skeleton active paragraph={{ rows: 6 }} />
        ) : (
          <List
            dataSource={data?.items ?? []}
            renderItem={(item: any) => (
              <List.Item
                onClick={() => navigate(`/crypto/${item.code}`)}
                style={{ cursor: 'pointer' }}
              >
                <List.Item.Meta
                  title={<InstrumentCodeTag code={item.code} name={item.name} />}
                  description={
                    <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>
                      {item.category} · {item.exchange}
                    </span>
                  }
                />
                <div style={{ textAlign: 'right' }}>
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontWeight: 600,
                      color: 'var(--text-secondary)',
                    }}
                  >
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
            }}
          />
        )
      ) : (
        <Table
          columns={columns}
          dataSource={data?.items ?? []}
          rowKey="code"
          loading={isLoading}
          onRow={(record) => ({
            onClick: () => navigate(`/crypto/${record.code}`),
            style: { cursor: 'pointer' },
          })}
          pagination={{
            current: page,
            pageSize: 50,
            total: data?.total ?? 0,
            onChange: setPage,
            showSizeChanger: false,
          }}
        />
      )}
    </div>
  );
}
