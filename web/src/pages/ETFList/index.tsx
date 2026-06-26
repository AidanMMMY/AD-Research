import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Input, Select, Row, Col, List, Tag, Skeleton } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useETFList, useETFCategories, useETFMarkets } from '@/hooks/useETFList';
import GlassCard from '@/components/GlassCard';
import ETFCodeTag from '@/components/ETFCodeTag';
import { useIsMobile } from '@/hooks/useBreakpoint';

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
  const { data: categories } = useETFCategories();
  const { data: markets } = useETFMarkets();

  const columns = [
    {
      title: '标的',
      render: (_: unknown, record: any) => <ETFCodeTag code={record.code} name={record.name} />,
    },
    {
      title: '分类',
      dataIndex: 'category',
      render: (v: string) => v ? (
        <span style={{ fontSize: 12, color: '#94a3b8', background: 'rgba(255,255,255,0.04)', padding: '2px 10px', borderRadius: 6 }}>
          {v}
        </span>
      ) : '-',
    },
    {
      title: '市场',
      dataIndex: 'market',
      width: 80,
      render: (v: string) => (
        <span style={{ fontSize: 12, color: '#64748b', fontFamily: "'SF Mono', monospace" }}>{v}</span>
      ),
    },
    {
      title: '类型',
      dataIndex: 'instrument_type',
      width: 70,
      render: (v: string) => v === 'STOCK' ? (
        <Tag style={{ margin: 0, fontSize: 11, borderRadius: 6 }} color="blue">个股</Tag>
      ) : (
        <Tag style={{ margin: 0, fontSize: 11, borderRadius: 6 }} color="purple">ETF</Tag>
      ),
    },
    {
      title: '管理公司',
      dataIndex: 'fund_manager',
      render: (v: string) => v ? (
        <span style={{ fontSize: 13, color: '#e2e8f0' }}>{v}</span>
      ) : '-',
    },
    {
      title: '跟踪指数',
      dataIndex: 'underlying_index',
      render: (v: string) => v ? (
        <span style={{ fontSize: 12, color: '#64748b', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', display: 'inline-block' }}>
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
          if (cap >= 1e12) return <span style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', fontFamily: "'SF Mono', monospace" }}>{(cap / 1e12).toFixed(2)}T</span>;
          if (cap >= 1e9) return <span style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', fontFamily: "'SF Mono', monospace" }}>{(cap / 1e9).toFixed(1)}B</span>;
          if (cap >= 1e6) return <span style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', fontFamily: "'SF Mono', monospace" }}>{(cap / 1e6).toFixed(1)}M</span>;
        }
        if (v) return (
          <span style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', fontFamily: "'SF Mono', monospace" }}>
            {(v / 1e8).toFixed(1)}亿
          </span>
        );
        return '-';
      },
      width: 110,
    },
  ];

  return (
    <div>
      <GlassCard>
        <Row gutter={[16, 16]} style={{ marginBottom: 4 }}>
          <Col xs={24} sm={8} md={6}>
            <Input
              placeholder="搜索标的代码或名称"
              allowClear
              prefix={<SearchOutlined style={{ color: '#475569' }} />}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={12} sm={8} md={5}>
            <Select
              placeholder="市场"
              allowClear
              style={{ width: '100%' }}
              options={markets?.map((m: string) => ({ label: m, value: m }))}
              onChange={(v) => { setMarket(v); setPage(1); }}
            />
          </Col>
          <Col xs={12} sm={8} md={6}>
            <Select
              placeholder="分类"
              allowClear
              style={{ width: '100%' }}
              options={categories?.map((c: string) => ({ label: c, value: c }))}
              onChange={(v) => { setCategory(v); setPage(1); }}
            />
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Select
              placeholder="类型"
              allowClear
              style={{ width: '100%' }}
              options={[
                { label: 'ETF', value: 'ETF' },
                { label: '个股', value: 'STOCK' },
              ]}
              value={instrumentType}
              onChange={(v) => { setInstrumentType(v); setPage(1); }}
            />
          </Col>
          <Col xs={0} sm={0} md={7} style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
            <span style={{ fontSize: 13, color: '#64748b' }}>
              共 <span style={{ color: '#818cf8', fontWeight: 700 }}>{data?.total || 0}</span> 只
            </span>
          </Col>
          <Col xs={24} sm={24} md={0} style={{ display: 'flex', alignItems: 'center' }}>
            <span style={{ fontSize: 13, color: '#64748b' }}>
              共 <span style={{ color: '#818cf8', fontWeight: 700 }}>{data?.total || 0}</span> 只
            </span>
          </Col>
        </Row>
      </GlassCard>

      <div style={{ marginTop: 20 }}>
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
                  background: 'rgba(255,255,255,0.03)',
                  border: '1px solid rgba(255,255,255,0.06)',
                  borderRadius: 12,
                  padding: '14px 16px',
                  marginBottom: 10,
                  cursor: 'pointer',
                  transition: 'all 200ms',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 8,
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = 'rgba(255,255,255,0.12)';
                  e.currentTarget.style.background = 'rgba(255,255,255,0.05)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'rgba(255,255,255,0.06)';
                  e.currentTarget.style.background = 'rgba(255,255,255,0.03)';
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <ETFCodeTag code={item.code} name={item.name} />
                  <span style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', fontFamily: "'SF Mono', monospace" }}>
                    {item.fund_size ? `${(item.fund_size / 1e8).toFixed(1)}亿` : '-'}
                  </span>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {item.category && (
                    <Tag style={{ margin: 0, fontSize: 11 }}>{item.category}</Tag>
                  )}
                  {item.market && (
                    <Tag style={{ margin: 0, fontSize: 11 }}>{item.market}</Tag>
                  )}
                  {item.fund_manager && (
                    <span style={{ fontSize: 12, color: '#64748b' }}>{item.fund_manager}</span>
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
              style: { textAlign: 'center', marginTop: 16 },
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
