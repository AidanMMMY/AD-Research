import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Input, Select, List, Skeleton } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useETFList, useETFCategories, useETFMarkets } from '@/hooks/useETFList';
import { useSparkline } from '@/hooks/useSparkline';
import ETFCodeTag from '@/components/ETFCodeTag';
import ThemeTag from '@/components/ThemeTag';
import Sparkline from '@/components/Sparkline';
import { useIsMobile } from '@/hooks/useBreakpoint';

/** Row-level sparkline cell. Owns its own query so per-row caching
 *  works without re-fetching the whole list. */
function SparklineCell({ code }: { code: string }) {
  const { data } = useSparkline({ code, days: 30 });
  if (!data || !data.points || data.points.length === 0) {
    return <span style={{ color: 'var(--text-tertiary)', fontSize: 11 }}>-</span>;
  }
  return <Sparkline data={data.points} width={80} height={20} />;
}

export default function ETFList() {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const [search, setSearch] = useState('');
  const [market, setMarket] = useState<string | undefined>();
  const [category, setCategory] = useState<string | undefined>();
  const [instrumentType, setInstrumentType] = useState<string | undefined>();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useETFList({
    search: search || undefined,
    market,
    category,
    instrument_type: instrumentType,
    page,
    page_size: 50,
  });
  const { data: categories } = useETFCategories({
    market,
    instrument_type: instrumentType,
  });
  const { data: markets } = useETFMarkets();

  // Clear the selected category if it no longer exists under the current
  // market / instrument type filters.
  useEffect(() => {
    if (category && categories && !categories.includes(category)) {
      setCategory(undefined);
    }
  }, [categories, category]);

  const columns = [
    {
      title: '标的',
      render: (_: unknown, record: any) => <ETFCodeTag code={record.code} name={record.name} />,
    },
    {
      title: '分类',
      dataIndex: 'category',
      render: (v: string) => v ? <ThemeTag>{v}</ThemeTag> : '-',
    },
    {
      title: '市场',
      dataIndex: 'market',
      width: 80,
      render: (v: string) => (
        <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{v}</span>
      ),
    },
    {
      title: '类型',
      dataIndex: 'instrument_type',
      width: 70,
      render: (v: string) => {
        const labelMap: Record<string, string> = {
          STOCK: '个股',
          CRYPTO: '数字货币',
          ETF: 'ETF',
        };
        const variantMap: Record<string, 'accent' | 'default'> = {
          STOCK: 'accent',
          CRYPTO: 'accent',
          ETF: 'default',
        };
        return <ThemeTag variant={variantMap[v] || 'default'}>{labelMap[v] || v}</ThemeTag>;
      },
    },
    {
      title: '管理公司',
      dataIndex: 'fund_manager',
      render: (v: string) => v ? (
        <span style={{ fontSize: 'var(--text-body-size)', color: 'var(--text-secondary)' }}>{v}</span>
      ) : '-',
    },
    {
      title: '跟踪指数',
      dataIndex: 'underlying_index',
      render: (v: string) => v ? (
        <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-secondary)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', display: 'inline-block' }}>
          {v}
        </span>
      ) : '-',
    },
    {
      title: '规模',
      dataIndex: 'fund_size',
      render: (v: number, record: any) => {
        // For US stocks, show market cap in USD; for ETFs show fund size
        if (record.market_cap) {
          const cap = record.market_cap;
          if (cap >= 1e12) return <span style={{ fontSize: 'var(--text-body-size)', fontWeight: 600, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{(cap / 1e12).toFixed(2)}T</span>;
          if (cap >= 1e9) return <span style={{ fontSize: 'var(--text-body-size)', fontWeight: 600, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{(cap / 1e9).toFixed(1)}B</span>;
          if (cap >= 1e6) return <span style={{ fontSize: 'var(--text-body-size)', fontWeight: 600, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{(cap / 1e6).toFixed(1)}M</span>;
        }
        if (v) return (
          <span style={{ fontSize: 'var(--text-body-size)', fontWeight: 600, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
            {(v / 1e8).toFixed(1)}亿
          </span>
        );
        return '-';
      },
      width: 110,
    },
    {
      title: '近 30 日',
      key: 'sparkline_30d',
      width: 100,
      render: (_: unknown, record: any) => <SparklineCell code={record.code} />,
    },
  ];

  return (
    <div>
      <h1 style={{ fontSize: 'var(--text-h1-size)', fontWeight: 500, color: 'var(--text-primary)', margin: '0 0 8px', letterSpacing: '-0.03em' }}>标的列表</h1>
      <p style={{ margin: '0 0 32px', color: 'var(--text-tertiary)', fontSize: 'var(--text-body-size)' }}>浏览和搜索全市场标的，按市场、分类、类型筛选</p>
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
          placeholder="搜索标的代码或名称"
          allowClear
          prefix={<SearchOutlined style={{ color: 'var(--text-tertiary)' }} />}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          style={{ width: 240 }}
        />
        <Select
          placeholder="市场"
          allowClear
          style={{ width: 140 }}
          options={markets?.map((m: string) => ({ label: m, value: m }))}
          onChange={(v) => { setMarket(v); setPage(1); }}
        />
        <Select
          placeholder="类型"
          allowClear
          style={{ width: 120 }}
          options={[
            { label: 'ETF', value: 'ETF' },
            { label: '个股', value: 'STOCK' },
            { label: '数字货币', value: 'CRYPTO' },
          ]}
          value={instrumentType}
          onChange={(v) => { setInstrumentType(v); setPage(1); }}
        />
        <Select
          placeholder="分类"
          allowClear
          style={{ width: 160 }}
          options={categories?.map((c: string) => ({ label: c, value: c }))}
          onChange={(v) => { setCategory(v); setPage(1); }}
        />
        <div style={{ marginLeft: 'auto', fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>
          共 <span style={{ color: 'var(--accent)', fontWeight: 500 }}>{data?.total || 0}</span> 只
        </div>
      </div>

      <div>
        {isLoading ? (
          <Skeleton active paragraph={{ rows: 10 }} />
        ) : isMobile ? (
          /* Mobile: card-style list */
          <List
            dataSource={data?.items || []}
            renderItem={(item: any) => (
              <div
                onClick={() => navigate(`/etfs/${item.code}`)}
                style={{
                  borderBottom: '1px solid var(--border-default)',
                  padding: 'var(--space-3) 0',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 'var(--space-2)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <ETFCodeTag code={item.code} name={item.name} />
                  <span style={{ fontSize: 'var(--text-body-size)', fontWeight: 600, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                    {item.fund_size ? `${(item.fund_size / 1e8).toFixed(1)}亿` : '-'}
                  </span>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
                  {item.category && (
                    <ThemeTag>{item.category}</ThemeTag>
                  )}
                  {item.market && (
                    <ThemeTag>{item.market}</ThemeTag>
                  )}
                  {item.fund_manager && (
                    <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>{item.fund_manager}</span>
                  )}
                </div>
              </div>
            )}
            pagination={{
              current: page,
              pageSize: 50,
              total: data?.total || 0,
              onChange: setPage,
              showSizeChanger: false,
              style: { textAlign: 'center', marginTop: 'var(--space-4)' },
            }}
          />
        ) : (
          /* Desktop: table view */
          <Table
            dataSource={data?.items || []}
            columns={columns}
            rowKey="code"
            loading={isLoading}
            scroll={{ x: 'max-content' }}
            pagination={{
              current: page,
              pageSize: 50,
              total: data?.total || 0,
              onChange: setPage,
              showSizeChanger: false,
            }}
            onRow={(record) => ({
              onClick: () => navigate(`/etfs/${record.code}`),
            })}
          />
        )}
      </div>
    </div>
  );
}
