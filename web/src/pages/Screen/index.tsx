import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Space, Select, InputNumber, Button, Tag, Row, Col } from 'antd';
import { useScreenResults, useScreenPresets, useScreenCategories } from '@/hooks/useScreenResults';
import { useETFMarkets } from '@/hooks/useETFList';
import { useScreenStore } from '@/stores/screen';
import { useAIHelp } from '@/hooks/useAIHelp';
import Panel from '@/components/Panel';
import HelpTrigger from '@/components/HelpTrigger';
import HelpPopover from '@/components/HelpPopover';
import ETFCodeTag from '@/components/ETFCodeTag';
import ReturnTag from '@/components/ReturnTag';
import { buildScreenContext } from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';

/** Map market codes to display labels */
const MARKET_LABELS: Record<string, string> = {
  'A股': 'A股',
  'US': '美股',
  'HK': '港股',
  'JP': '日股',
};


export default function Screen() {
  const navigate = useNavigate();
  const { open } = useAIHelp();
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

  const handleOpenHelp = () => {
    open({
      pageType: 'screen',
      pageTitle: '全市场筛选器',
      contextData: buildScreenContext(filters, preset, results),
      quickQuestions: getQuickQuestions('screen'),
    });
  };

  const columns = [
    { title: '代码', dataIndex: 'code', width: 100, render: (v: string, r: any) => <ETFCodeTag code={v} name={r.name} /> },
    { title: '分类', dataIndex: 'category', width: 100, render: (v: string) => v ? <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-secondary)' }}>{v}</span> : '-' },
    { title: <HelpPopover termKey="composite_score_filter">评分</HelpPopover>, dataIndex: 'composite_score', width: 80, render: (v: number) => <span style={{ fontWeight: 700, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>{v?.toFixed(1)}</span> },
    { title: <HelpPopover termKey="rsi14">RSI</HelpPopover>, dataIndex: 'rsi14', width: 70, render: (v: number) => <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{v?.toFixed(1)}</span> },
    { title: <HelpPopover termKey="sharpe_1y">夏普</HelpPopover>, dataIndex: 'sharpe_1y', width: 80, render: (v: number) => <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{v?.toFixed(2)}</span> },
    { title: <HelpPopover termKey="return_1m">1月</HelpPopover>, dataIndex: 'return_1m', width: 100, render: (v: number) => <ReturnTag value={v} /> },
    { title: <HelpPopover termKey="return_3m">3月</HelpPopover>, dataIndex: 'return_3m', width: 100, render: (v: number) => <ReturnTag value={v} /> },
    { title: <HelpPopover termKey="return_1y">1年</HelpPopover>, dataIndex: 'return_1y', width: 100, render: (v: number) => <ReturnTag value={v} /> },
    { title: <HelpPopover termKey="volatility_20d">波动率</HelpPopover>, dataIndex: 'volatility_20d', width: 90, render: (v: number) => v ? <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{v.toFixed(1)}%</span> : '-' },
  ];

  return (
    <div>
      <Panel
        title="筛选条件"
        extra={<HelpTrigger tooltip="AI 解释筛选逻辑" onClick={handleOpenHelp} />}
      >
        <div style={{ marginBottom: 16 }}>
          <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-secondary)', marginRight: 12 }}>
            <HelpPopover termKey="screen_presets">快速筛选</HelpPopover>:
          </span>
          {presets?.map((p) => (
            <Tag
              key={p.key}
              style={{
                cursor: 'pointer',
                borderRadius: 'var(--radius-md)',
                padding: '3px 12px',
                fontSize: 'var(--text-small-size)',
                border: `1px solid ${preset === p.key ? 'var(--accent-border)' : 'var(--border-default)'}`,
                background: preset === p.key ? 'var(--accent-dim)' : 'var(--bg-input)',
                color: preset === p.key ? 'var(--accent)' : 'var(--text-secondary)',
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
          <span style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-small-size)' }}>
            共 <span style={{ color: 'var(--accent)', fontWeight: 700 }}>{results?.count || 0}</span> 只
            {(results?.count || 0) > pageSize && (
              <span style={{ color: 'var(--text-tertiary)', marginLeft: 8 }}>
                (第 {page}/{Math.ceil((results?.count || 0) / pageSize)} 页)
              </span>
            )}
          </span>
        </Space>
      </Panel>

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
