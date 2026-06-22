import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Input, Select, Row, Col } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useETFList, useETFCategories, useETFMarkets } from '@/hooks/useETFList';
import GlassCard from '@/components/GlassCard';
import ETFCodeTag from '@/components/ETFCodeTag';

export default function ETFList() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [market, setMarket] = useState<string | undefined>();
  const [category, setCategory] = useState<string | undefined>();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useETFList({ search: search || undefined, market, category, page, page_size: 50 });
  const { data: categories } = useETFCategories();
  const { data: markets } = useETFMarkets();

  const columns = [
    {
      title: 'ETF',
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
      render: (v: number) => v ? (
        <span style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', fontFamily: "'SF Mono', monospace" }}>
          {(v / 1e8).toFixed(1)}亿
        </span>
      ) : '-',
      width: 100,
    },
  ];

  return (
    <div>
      <GlassCard>
        <Row gutter={[16, 16]} style={{ marginBottom: 4 }}>
          <Col xs={24} sm={8} md={6}>
            <Input
              placeholder="搜索ETF代码或名称"
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
          <Col xs={24} sm={24} md={7} style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
            <span style={{ fontSize: 13, color: '#64748b' }}>
              共 <span style={{ color: '#818cf8', fontWeight: 700 }}>{data?.total || 0}</span> 只ETF
            </span>
          </Col>
        </Row>
      </GlassCard>

      <div style={{ marginTop: 20 }}>
        <Table
          dataSource={data?.items || []}
          columns={columns}
          rowKey="code"
          loading={isLoading}
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
      </div>
    </div>
  );
}
