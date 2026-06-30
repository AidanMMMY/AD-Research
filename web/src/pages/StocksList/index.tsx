import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Input, Select, List, Skeleton } from 'antd';
import { SearchOutlined, StockOutlined } from '@ant-design/icons';
import { useStockList } from '@/hooks/useStocks';
import { useETFMarkets, useETFCategories } from '@/hooks/useETFList';
import { useSparkline } from '@/hooks/useSparkline';
import ETFCodeTag from '@/components/ETFCodeTag';
import ThemeTag from '@/components/ThemeTag';
import Sparkline from '@/components/Sparkline';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { useDensity } from '@/hooks/useDensity';

/** Row-level sparkline cell. Uses the shared ETF sparkline endpoint
 *  which works for any instrument via instrument_daily_bar. */
function SparklineCell({ code }: { code: string }) {
  const { data } = useSparkline({ code, days: 30 });
  if (!data || !data.points || data.points.length === 0) {
    return <span style={{ color: 'var(--text-tertiary)', fontSize: 11 }}>-</span>;
  }
  return <Sparkline data={data.points} width={80} height={20} />;
}

export default function StocksList() {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const { density } = useDensity();
  const [search, setSearch] = useState('');
  const [market, setMarket] = useState<string | undefined>('A股');
  const [category, setCategory] = useState<string | undefined>();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useStockList({
    search: search || undefined,
    market,
    category,
    page,
    page_size: 50,
  });
  const { data: categories } = useETFCategories({
    market,
    instrument_type: 'STOCK',
  });
  const { data: markets } = useETFMarkets();

  // Reset category if it disappears under current filters.
  useEffect(() => {
    if (category && categories && !categories.includes(category)) {
      setCategory(undefined);
    }
  }, [categories, category]);

  const rowSize = density === 'dense' ? 'small' : density === 'spacious' ? 'large' : 'middle';

  const columns = [
    {
      title: '代码',
      dataIndex: 'code',
      width: 110,
      render: (_: unknown, record: any) => <ETFCodeTag code={record.code} name={record.name} />,
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
      title: '行业',
      dataIndex: 'industry',
      width: 140,
      render: (v: string) => v ? <ThemeTag>{v}</ThemeTag> : <span style={{ color: 'var(--text-tertiary)' }}>-</span>,
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 120,
      render: (v: string) => v ? <ThemeTag>{v}</ThemeTag> : <span style={{ color: 'var(--text-tertiary)' }}>-</span>,
    },
    {
      title: '市值',
      dataIndex: 'market_cap',
      width: 110,
      render: (v: number) => {
        if (!v) return <span style={{ color: 'var(--text-tertiary)' }}>-</span>;
        if (v >= 1e12) return <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-secondary)' }}>{(v / 1e12).toFixed(2)}T</span>;
        if (v >= 1e9) return <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-secondary)' }}>{(v / 1e9).toFixed(1)}B</span>;
        if (v >= 1e8) return <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-secondary)' }}>{(v / 1e8).toFixed(1)}亿</span>;
        return <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{(v / 1e4).toFixed(0)}万</span>;
      },
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
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 8 }}>
        <StockOutlined style={{ fontSize: 22, color: 'var(--accent)' }} />
        <h1 style={{ fontSize: 'var(--text-h1-size)', fontWeight: 500, color: 'var(--text-primary)', margin: 0, letterSpacing: '-0.03em' }}>
          个股列表
        </h1>
      </div>
      <p style={{ margin: '0 0 32px', color: 'var(--text-tertiary)', fontSize: 'var(--text-body-size)' }}>
        浏览和搜索全市场 A 股个股，按市场、行业筛选
      </p>
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
          placeholder="搜索代码或名称"
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
          value={market}
          onChange={(v) => { setMarket(v); setPage(1); }}
        />
        <Select
          placeholder="行业"
          allowClear
          style={{ width: 180 }}
          options={categories?.map((c: string) => ({ label: c, value: c }))}
          value={category}
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
          <List
            dataSource={data?.items || []}
            renderItem={(item: any) => (
              <div
                onClick={() => navigate(`/stocks/${item.code}`)}
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
                  {item.market_cap ? (
                    <span style={{ fontSize: 'var(--text-body-size)', fontWeight: 600, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                      {item.market_cap >= 1e8 ? `${(item.market_cap / 1e8).toFixed(1)}亿` : `${(item.market_cap / 1e4).toFixed(0)}万`}
                    </span>
                  ) : null}
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
                  {item.industry && <ThemeTag>{item.industry}</ThemeTag>}
                  {item.category && <ThemeTag>{item.category}</ThemeTag>}
                  {item.market && <ThemeTag>{item.market}</ThemeTag>}
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
          <Table
            dataSource={data?.items || []}
            columns={columns}
            rowKey="code"
            loading={isLoading}
            size={rowSize as any}
            scroll={{ x: 'max-content' }}
            pagination={{
              current: page,
              pageSize: 50,
              total: data?.total || 0,
              onChange: setPage,
              showSizeChanger: false,
            }}
            onRow={(record) => ({
              onClick: () => navigate(`/stocks/${record.code}`),
            })}
          />
        )}
      </div>
    </div>
  );
}
