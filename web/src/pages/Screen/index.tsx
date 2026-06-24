import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Space, Select, InputNumber, Button, Tag, Row, Col } from 'antd';
import { useScreenResults, useScreenPresets, useScreenCategories } from '@/hooks/useScreenResults';
import { useETFMarkets } from '@/hooks/useETFList';
import { useScreenStore } from '@/stores/screen';
import GlassCard from '@/components/GlassCard';
import ETFCodeTag from '@/components/ETFCodeTag';
import ReturnTag from '@/components/ReturnTag';

/** Map market codes to display labels */
const MARKET_LABELS: Record<string, string> = {
  'A股': 'A股',
  'US': '美股',
  'HK': '港股',
  'JP': '日股',
};


export default function Screen() {
  const navigate = useNavigate();
  const { filters, preset, setFilter, resetFilters, applyPreset } = useScreenStore();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  // Include pagination and active preset in API request
  const queryFilters = useMemo(
    () => ({
      ...filters,
      ...(preset ? { preset } : {}),
      offset: (page - 1) * pageSize,
      limit: pageSize,
    }),
    [filters, preset, page, pageSize]
  );
  const { data: results, isLoading } = useScreenResults(queryFilters);
  const { data: presets } = useScreenPresets();
  const { data: categories } = useScreenCategories();
  const { data: markets } = useETFMarkets();

  const columns = [
    { title: '代码', dataIndex: 'code', width: 100, render: (v: string, r: any) => <ETFCodeTag code={v} name={r.name} /> },
    { title: '分类', dataIndex: 'category', width: 100, render: (v: string) => v ? <span style={{ fontSize: 12, color: '#94a3b8' }}>{v}</span> : '-' },
    { title: '评分', dataIndex: 'composite_score', width: 80, render: (v: number) => <span style={{ fontWeight: 700, color: '#818cf8', fontFamily: "'SF Mono', monospace" }}>{v?.toFixed(1)}</span> },
    { title: 'RSI', dataIndex: 'rsi14', width: 70, render: (v: number) => <span style={{ fontFamily: "'SF Mono', monospace", color: '#94a3b8' }}>{v?.toFixed(1)}</span> },
    { title: '夏普', dataIndex: 'sharpe_1y', width: 80, render: (v: number) => <span style={{ fontFamily: "'SF Mono', monospace", color: '#94a3b8' }}>{v?.toFixed(2)}</span> },
    { title: '1月', dataIndex: 'return_1m', width: 100, render: (v: number) => <ReturnTag value={v} /> },
    { title: '3月', dataIndex: 'return_3m', width: 100, render: (v: number) => <ReturnTag value={v} /> },
    { title: '1年', dataIndex: 'return_1y', width: 100, render: (v: number) => <ReturnTag value={v} /> },
    { title: '波动率', dataIndex: 'volatility_20d', width: 90, render: (v: number) => v ? <span style={{ fontFamily: "'SF Mono', monospace", color: '#94a3b8' }}>{v.toFixed(1)}%</span> : '-' },
  ];

  return (
    <div>
      <GlassCard>
        <div style={{ marginBottom: 16 }}>
          <span style={{ fontSize: 13, color: '#94a3b8', marginRight: 12 }}>快速筛选:</span>
          {presets?.map((p) => (
            <Tag
              key={p.key}
              style={{
                cursor: 'pointer',
                borderRadius: 8,
                padding: '3px 12px',
                fontSize: 12,
                border: `1px solid ${preset === p.key ? 'rgba(99,102,241,0.4)' : 'rgba(255,255,255,0.08)'}`,
                background: preset === p.key ? 'rgba(99,102,241,0.15)' : 'rgba(255,255,255,0.03)',
                color: preset === p.key ? '#818cf8' : '#94a3b8',
                transition: 'all 200ms',
              }}
              onClick={() => applyPreset(preset === p.key ? null : p.key)}
            >
              {p.name}
            </Tag>
          ))}
        </div>

        <Row gutter={[16, 12]}>
          <Col xs={12} sm={8} md={6}>
            <Select
              placeholder="市场"
              allowClear
              style={{ width: '100%' }}
              value={filters.market}
              options={(markets || []).map((m: string) => ({
                label: MARKET_LABELS[m] || m,
                value: m,
              }))}
              onChange={(v) => setFilter('market', v)}
            />
          </Col>
          <Col xs={12} sm={8} md={6}>
            <Select
              placeholder="分类"
              allowClear
              style={{ width: '100%' }}
              value={filters.category}
              options={categories?.map((c: any) => ({ label: `${c.category} (${c.count})`, value: c.category }))}
              onChange={(v) => setFilter('category', v)}
            />
          </Col>
          <Col xs={12} sm={8} md={6}>
            <InputNumber
              placeholder="评分最小"
              style={{ width: '100%' }}
              min={0} max={100}
              value={filters.score_min}
              onChange={(v) => setFilter('score_min', v || undefined)}
            />
          </Col>
          <Col xs={12} sm={8} md={6}>
            <InputNumber
              placeholder="RSI最小"
              style={{ width: '100%' }}
              min={0} max={100}
              value={filters.rsi_min}
              onChange={(v) => setFilter('rsi_min', v || undefined)}
            />
          </Col>
          <Col xs={12} sm={8} md={6}>
            <InputNumber
              placeholder="夏普最小"
              style={{ width: '100%' }}
              value={filters.sharpe_min}
              onChange={(v) => setFilter('sharpe_min', v || undefined)}
            />
          </Col>
          <Col xs={12} sm={8} md={6}>
            <InputNumber
              placeholder="波动率最大"
              style={{ width: '100%' }}
              value={filters.volatility_max}
              onChange={(v) => setFilter('volatility_max', v || undefined)}
            />
          </Col>
        </Row>

        <Space style={{ marginTop: 16 }}>
          <Button onClick={() => { resetFilters(); setPage(1); }}>重置条件</Button>
          <span style={{ color: '#64748b', fontSize: 13 }}>
            共 <span style={{ color: '#818cf8', fontWeight: 700 }}>{results?.count || 0}</span> 只
            {(results?.count || 0) > pageSize && (
              <span style={{ color: '#475569', marginLeft: 8 }}>
                (第 {page}/{Math.ceil((results?.count || 0) / pageSize)} 页)
              </span>
            )}
          </span>
        </Space>
      </GlassCard>

      <div style={{ marginTop: 20 }}>
        <Table
          dataSource={results?.items || []}
          columns={columns}
          rowKey="code"
          loading={isLoading}
          pagination={{
            current: page,
            pageSize: pageSize,
            total: results?.count || 0,
            pageSizeOptions: [20, 50, 100, 200],
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 只`,
            onChange: (newPage, newSize) => {
              setPage(newPage);
              if (newSize !== pageSize) {
                setPageSize(newSize);
                setPage(1);
              }
            },
          }}
          scroll={{ x: 'max-content' }}
          onRow={(record) => ({
            onClick: () => navigate(`/etfs/${record.code}`),
          })}
        />
      </div>
    </div>
  );
}
