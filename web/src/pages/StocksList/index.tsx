import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Input, Select, List, Skeleton } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useStockList } from '@/hooks/useStocks';
import { useInstrumentMarkets, useInstrumentCategories } from '@/hooks/useInstrumentList';
import { useSparkline } from '@/hooks/useSparkline';
import { useDensity } from '@/hooks/useDensity';
import { useDebounce } from '@/hooks/useDebounce';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import EmptyState from '@/components/EmptyState';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import ThemeTag from '@/components/ThemeTag';
import Sparkline from '@/components/Sparkline';
import { useIsMobile } from '@/hooks/useBreakpoint';

/** Row-level sparkline cell. Uses the shared ETF sparkline endpoint
 *  which works for any instrument via instrument_daily_bar. */
function SparklineCell({ code }: { code: string }) {
  const { data } = useSparkline({ code, days: 30 });
  if (!data || !data.points || data.points.length === 0) {
    return <span className="mobile-list-item__meta">-</span>;
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
  const debouncedSearch = useDebounce(search, 300);

  const { data, isLoading } = useStockList({
    search: debouncedSearch || undefined,
    market,
    category,
    page,
    page_size: 50,
  });
  const { data: categories } = useInstrumentCategories({
    market,
    instrument_type: 'STOCK',
  });
  const { data: markets } = useInstrumentMarkets();

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
      render: (_: unknown, record: any) => <InstrumentCodeTag code={record.code} name={record.name} />,
    },
    {
      title: '市场',
      dataIndex: 'market',
      width: 80,
      render: (v: string) => (
        <span className="tabular-nums mobile-list-item__meta font-mono">{v}</span>
      ),
    },
    {
      title: '行业',
      dataIndex: 'industry',
      width: 140,
      render: (v: string) => v ? <ThemeTag>{v}</ThemeTag> : <span className="mobile-list-item__meta">-</span>,
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 120,
      render: (v: string) => v ? <ThemeTag>{v}</ThemeTag> : <span className="mobile-list-item__meta">-</span>,
    },
    {
      title: '市值',
      dataIndex: 'market_cap',
      width: 110,
      render: (v: number) => {
        if (!v) return <span className="mobile-list-item__meta">-</span>;
        if (v >= 1e12) return <span className="tabular-nums mobile-list-item__value">{(v / 1e12).toFixed(2)}T</span>;
        if (v >= 1e9) return <span className="tabular-nums mobile-list-item__value">{(v / 1e9).toFixed(1)}B</span>;
        if (v >= 1e8) return <span className="tabular-nums mobile-list-item__value">{(v / 1e8).toFixed(1)}亿</span>;
        return <span className="tabular-nums mobile-list-item__meta">{(v / 1e4).toFixed(0)}万</span>;
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
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="全市场"
        title="个股列表"
        description="浏览和搜索全市场 A 股个股，按市场、行业筛选"
      />

      <FilterToolbar total={`共 ${data?.total || 0} 只`}>
        <Input
          placeholder="搜索代码或名称"
          allowClear
          prefix={<SearchOutlined className="ad-icon-tertiary" />}
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
      </FilterToolbar>

      <div>
        {isLoading ? (
          <Skeleton active paragraph={{ rows: 10 }} />
        ) : (data?.items?.length || 0) === 0 ? (
          <EmptyState
            title="没有符合条件的个股"
            description="尝试调整上方筛选条件，或清空搜索关键词查看全部个股"
          />
        ) : isMobile ? (
          <List
            dataSource={data?.items || []}
            renderItem={(item: any) => (
              <div
                onClick={() => navigate(`/stocks/${item.code}`)}
                className="mobile-list-item"
              >
                <div className="mobile-list-item__row">
                  <InstrumentCodeTag code={item.code} name={item.name} />
                  {item.market_cap ? (
                    <span className="tabular-nums mobile-list-item__value">
                      {item.market_cap >= 1e8 ? `${(item.market_cap / 1e8).toFixed(1)}亿` : `${(item.market_cap / 1e4).toFixed(0)}万`}
                    </span>
                  ) : null}
                </div>
                <div className="mobile-list-item__tags">
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
              className: 'mobile-list-pagination',
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
    </PageShell>
  );
}
