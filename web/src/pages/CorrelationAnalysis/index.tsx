import { useMemo, useState } from 'react';
import { Row, Col, Select, Button, Space, Spin, message } from 'antd';
import { FolderOpenOutlined } from '@ant-design/icons';
import GlassCard from '@/components/GlassCard';
import ThemeTag from '@/components/ThemeTag';
import { useQuery } from '@tanstack/react-query';
import { analysisApi } from '@/api/analysis';
import { useETFList } from '@/hooks/useETFList';
import { usePoolList } from '@/hooks/usePoolDetail';
import CorrelationHeatmap from '@/components/CorrelationHeatmap';

const WINDOW_OPTIONS = [
  { label: '30日', value: 30 },
  { label: '60日', value: 60 },
  { label: '120日', value: 120 },
  { label: '250日', value: 250 },
];

const METHOD_OPTIONS = [
  { label: 'Pearson', value: 'pearson' },
  { label: 'Spearman', value: 'spearman' },
];

const PRESET_TOP_N = 4;

interface ETFItem {
  code: string;
  name: string;
  category?: string;
  fund_size?: number;
}

export default function CorrelationAnalysis() {
  const [selectedCodes, setSelectedCodes] = useState<string[]>(['510300', '510050', '510500', '159915']);
  const [window, setWindow] = useState<number>(60);
  const [method, setMethod] = useState<'pearson' | 'spearman'>('pearson');

  const { data: etfList } = useETFList({ page_size: 200 });
  const { data: pools, isLoading: poolsLoading } = usePoolList();

  const presetGroups = useMemo(() => {
    const items: ETFItem[] = etfList?.items || [];
    const byCategory: Record<string, ETFItem[]> = {};
    items.forEach((item) => {
      const category = item.category || '未分类';
      if (!byCategory[category]) byCategory[category] = [];
      byCategory[category].push(item);
    });

    return Object.entries(byCategory)
      .sort(([a], [b]) => a.localeCompare(b, 'zh-CN'))
      .map(([category, members]) => ({
        label: category,
        codes: members
          .sort((a, b) => (b.fund_size || 0) - (a.fund_size || 0))
          .slice(0, PRESET_TOP_N)
          .map((item) => item.code),
      }))
      .filter((group) => group.codes.length > 0);
  }, [etfList]);

  const { data: correlationData, isLoading } = useQuery({
    queryKey: ['correlation', selectedCodes, window, method],
    queryFn: () =>
      analysisApi.correlation(selectedCodes, window, method).then((r) => r.data),
    enabled: selectedCodes.length >= 2,
    staleTime: 60_000,
  });

  const etfOptions = (etfList?.items || []).map((item) => ({
    label: `${item.code} ${item.name}`,
    value: item.code,
  }));

  const poolOptions = (pools || []).map((pool) => ({
    label: `${pool.name} (${pool.members?.length || 0}只)`,
    value: pool.id,
    codes: (pool.members || []).map((m) => m.etf_code),
  }));

  const handleAddPreset = (codes: string[]) => {
    const newCodes = Array.from(new Set([...selectedCodes, ...codes]));
    if (newCodes.length > 20) {
      message.warning('最多选择20只标的');
      return;
    }
    setSelectedCodes(newCodes);
  };

  const handleSelectPool = (poolId: number | undefined) => {
    if (!poolId) return;
    const pool = poolOptions.find((p) => p.value === poolId);
    if (!pool) return;
    const newCodes = Array.from(new Set([...selectedCodes, ...pool.codes]));
    if (newCodes.length > 20) {
      message.warning('标的池成员数量较多，仅添加前20只');
      setSelectedCodes(newCodes.slice(0, 20));
      return;
    }
    setSelectedCodes(newCodes);
    message.success(`已添加「${pool.label}」中的 ${pool.codes.length} 只标的`);
  };

  const handleRemoveCode = (code: string) => {
    setSelectedCodes(selectedCodes.filter((c) => c !== code));
  };

  return (
    <div>
      <h1 style={{ fontSize: 'var(--text-h1-size)', fontWeight: 500, color: 'var(--text-primary)', margin: '0 0 8px', letterSpacing: '-0.03em' }}>相关性分析</h1>
      <p style={{ margin: '0 0 32px', color: 'var(--text-tertiary)', fontSize: 'var(--text-body-size)' }}>分析多只标的之间的价格相关性，支持多种计算方法和时间窗口</p>
      <GlassCard title="相关性分析配置" style={{ marginBottom: 'var(--space-4)' }}>
        <Row gutter={[16, 16]}>
          <Col xs={24} md={12}>
            <div style={{ marginBottom: 8 }}>选择标的（{selectedCodes.length}/20）：</div>
            <Select
              mode="multiple"
              showSearch
              placeholder="搜索并选择标的"
              value={selectedCodes}
              onChange={setSelectedCodes}
              options={etfOptions}
              style={{ width: '100%' }}
              maxTagCount={0}
              tagRender={() => <span />}
              filterOption={(input, option) =>
                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
            />
            {selectedCodes.length > 0 && (
              <div style={{ marginTop: 10 }}>
                <Space size={[8, 8]} wrap>
                  {selectedCodes.map((code) => (
                    <ThemeTag key={code} variant="accent" style={{ cursor: 'default' }}>
                      {code}
                      <span
                        style={{ marginLeft: 6, cursor: 'pointer', fontWeight: 500 }}
                        onClick={() => handleRemoveCode(code)}
                      >
                        ×
                      </span>
                    </ThemeTag>
                  ))}
                </Space>
              </div>
            )}
          </Col>
          <Col xs={24} md={6}>
            <div style={{ marginBottom: 8 }}>窗口期：</div>
            <Select
              value={window}
              onChange={setWindow}
              options={WINDOW_OPTIONS}
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={24} md={6}>
            <div style={{ marginBottom: 8 }}>计算方法：</div>
            <Select
              value={method}
              onChange={setMethod}
              options={METHOD_OPTIONS}
              style={{ width: '100%' }}
            />
          </Col>
        </Row>
        <Row style={{ marginTop: 16 }}>
          <Col span={24}>
            <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
              <span style={{ flexShrink: 0, color: 'var(--text-secondary)', fontSize: 'var(--text-body-size)', paddingTop: 4 }}>
                快速选择：
              </span>
              <Space size={[8, 8]} wrap>
                {presetGroups.map((group) => (
                  <Button key={group.label} size="small" onClick={() => handleAddPreset(group.codes)}>
                    +{group.label}
                  </Button>
                ))}
                <Select
                  size="small"
                  placeholder={<span><FolderOpenOutlined /> 从标的池导入</span>}
                  style={{ minWidth: 160 }}
                  loading={poolsLoading}
                  onChange={handleSelectPool}
                  options={poolOptions}
                  allowClear
                />
                <Button size="small" danger onClick={() => setSelectedCodes([])}>
                  清空
                </Button>
              </Space>
            </div>
          </Col>
        </Row>
      </GlassCard>

      <GlassCard title="相关性热力图">
        {selectedCodes.length < 2 ? (
          <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-secondary)' }}>
            请至少选择2只标的进行分析
          </div>
        ) : isLoading ? (
          <Spin size="large" style={{ display: 'block', margin: '60px auto' }} />
        ) : correlationData ? (
          <CorrelationHeatmap codes={correlationData.codes} matrix={correlationData.matrix} />
        ) : null}
      </GlassCard>
    </div>
  );
}
