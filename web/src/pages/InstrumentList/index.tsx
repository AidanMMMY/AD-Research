import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Input, Select, List, Skeleton } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useInstrumentList, useInstrumentCategories, useInstrumentMarkets } from '@/hooks/useInstrumentList';
import { useSparkline } from '@/hooks/useSparkline';
import { useMarketStream } from '@/hooks/useMarketStream';
import { useDensity } from '@/hooks/useDensity';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import EmptyState from '@/components/EmptyState';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import ThemeTag from '@/components/ThemeTag';
import Sparkline from '@/components/Sparkline';
import ReturnTag from '@/components/ReturnTag';
import LastUpdated from '@/components/LastUpdated';
import { useIsMobile } from '@/hooks/useBreakpoint';

/** Row-level sparkline cell. Owns its own query so per-row caching
 *  works without re-fetching the whole list. */
function SparklineCell({ code }: { code: string }) {
  const { data } = useSparkline({ code, days: 30 });
  if (!data || !data.points || data.points.length === 0) {
    return <span className="mobile-list-item__meta">-</span>;
  }
  return <Sparkline data={data.points} width={80} height={20} />;
}

/** Row-level live price cell. Reads from the shared MarketStream map so we
 *  do not open one SSE connection per row. */
function LivePriceCell({ tick }: { code: string; tick: ReturnType<typeof useMarketStream>['latest'][string] | undefined }) {
  if (!tick) {
    return (
      <span className="tabular-nums mobile-list-item__meta font-mono">
        -
      </span>
    );
  }
  return (
    <div className="live-price-cell">
      <span className="tabular-nums live-price-cell__price">
        {tick.price.toFixed(2)}
      </span>
      <ReturnTag value={tick.change_pct} />
    </div>
  );
}

export default function InstrumentList() {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const { density } = useDensity();
  const [search, setSearch] = useState('');
  const [market, setMarket] = useState<string | undefined>();
  const [category, setCategory] = useState<string | undefined>();
  const [instrumentType, setInstrumentType] = useState<string | undefined>();
  const [page, setPage] = useState(1);

  const { data, isLoading, dataUpdatedAt, isFetching } = useInstrumentList({
    search: search || undefined,
    market,
    category,
    instrument_type: instrumentType,
    page,
    page_size: 50,
  });
  const { data: categories } = useInstrumentCategories({
    market,
    instrument_type: instrumentType,
  });
  const { data: markets } = useInstrumentMarkets();

  // Clear the selected category if it no longer exists under the current
  // market / instrument type filters.
  useEffect(() => {
    if (category && categories && !categories.includes(category)) {
      setCategory(undefined);
    }
  }, [categories, category]);

  // Stream live prices for the current page only. The backend page_size is
  // already capped at 50, so this keeps the SSE query param list small and
  // avoids re-subscribing on every keystroke in the search box.
  const pageCodes = useMemo(
    () => (data?.items || []).map((it: { code: string }) => it.code).filter(Boolean),
    [data?.items]
  );
  const { latest: liveLatest } = useMarketStream(pageCodes);

  const rowSize = density === 'dense' ? 'small' : density === 'spacious' ? 'large' : 'middle';

  const columns = [
    {
      title: '标的',
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
      title: '市场',
      dataIndex: 'market',
      width: 80,
      render: (v: string) => (
        <span className="tabular-nums mobile-list-item__meta font-mono">{v}</span>
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
        <span className="ad-text-secondary">{v}</span>
      ) : '-',
    },
    {
      title: '跟踪指数',
      dataIndex: 'underlying_index',
      render: (v: string) => v ? (
        <span className="mobile-list-item__meta instrument-index-cell">
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
          if (cap >= 1e12) return <span className="tabular-nums mobile-list-item__value">{(cap / 1e12).toFixed(2)}T</span>;
          if (cap >= 1e9) return <span className="tabular-nums mobile-list-item__value">{(cap / 1e9).toFixed(1)}B</span>;
          if (cap >= 1e6) return <span className="tabular-nums mobile-list-item__value">{(cap / 1e6).toFixed(1)}M</span>;
        }
        if (v) return (
          <span className="tabular-nums mobile-list-item__value">
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
    {
      title: '实时价',
      key: 'live_price',
      width: 110,
      render: (_: unknown, record: any) => (
        <LivePriceCell code={record.code} tick={liveLatest[record.code]} />
      ),
    },
  ];

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="全市场"
        title="标的列表"
        description="浏览和搜索全市场标的，按市场、分类、类型筛选"
        extra={<LastUpdated at={dataUpdatedAt} loading={isFetching && !data} />}
      />

      <FilterToolbar total={`共 ${data?.total || 0} 只`}>
        <Input
          placeholder="搜索标的代码或名称"
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
      </FilterToolbar>

      <div>
        {isLoading ? (
          <Skeleton active paragraph={{ rows: 10 }} />
        ) : (data?.items?.length || 0) === 0 ? (
          <EmptyState
            title="没有符合条件的标的"
            description="尝试调整上方筛选条件，或清空搜索关键词查看全部标的"
          />
        ) : isMobile ? (
          /* Mobile: card-style list */
          <List
            dataSource={data?.items || []}
            renderItem={(item: any) => (
              <div
                onClick={() => navigate(`/instruments/${item.code}`)}
                className="mobile-list-item"
              >
                <div className="mobile-list-item__row">
                  <InstrumentCodeTag code={item.code} name={item.name} name_zh={item.name_zh} />
                  <span className="tabular-nums mobile-list-item__value">
                    {item.fund_size ? `${(item.fund_size / 1e8).toFixed(1)}亿` : '-'}
                  </span>
                </div>
                <div className="mobile-list-item__row">
                  <LivePriceCell code={item.code} tick={liveLatest[item.code]} />
                </div>
                <div className="mobile-list-item__tags">
                  {item.category && (
                    <ThemeTag>{item.category}</ThemeTag>
                  )}
                  {item.market && (
                    <ThemeTag>{item.market}</ThemeTag>
                  )}
                  {item.fund_manager && (
                    <span className="mobile-list-item__meta">{item.fund_manager}</span>
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
              className: 'mobile-list-pagination',
            }}
          />
        ) : (
          /* Desktop: table view */
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
              onClick: () => navigate(`/instruments/${record.code}`),
            })}
          />
        )}
      </div>
    </PageShell>
  );
}
