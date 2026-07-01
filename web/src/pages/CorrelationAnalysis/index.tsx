import { useState } from 'react';
import { Row, Col, Select, Spin } from 'antd';
import GlassCard from '@/components/GlassCard';
import { useQuery } from '@tanstack/react-query';
import { analysisApi } from '@/api/analysis';
import InstrumentSelector from '@/components/InstrumentSelector';
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

export default function CorrelationAnalysis() {
  const [selectedCodes, setSelectedCodes] = useState<string[]>(['510300.SH', '510050.SH', '510500.SH', '159915.SZ']);
  const [window, setWindow] = useState<number>(60);
  const [method, setMethod] = useState<'pearson' | 'spearman'>('pearson');

  const { data: correlationData, isLoading } = useQuery({
    queryKey: ['correlation', selectedCodes, window, method],
    queryFn: () =>
      analysisApi.correlation(selectedCodes, window, method).then((r) => r.data),
    enabled: selectedCodes.length >= 2,
    staleTime: 60_000,
  });

  return (
    <div>
      <h1 style={{ fontSize: 'var(--text-h1-size)', fontWeight: 500, color: 'var(--text-primary)', margin: '0 0 8px', letterSpacing: '-0.03em' }}>相关性分析</h1>
      <p style={{ margin: '0 0 32px', color: 'var(--text-tertiary)', fontSize: 'var(--text-body-size)' }}>分析多只标的之间的价格相关性，支持多种计算方法和时间窗口</p>
      <GlassCard title="相关性分析配置" style={{ marginBottom: 'var(--space-4)' }}>
        <Row gutter={[16, 16]}>
          <Col xs={24} md={12}>
            <InstrumentSelector
              value={selectedCodes}
              onChange={setSelectedCodes}
              maxCount={20}
            />
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
      </GlassCard>

      <GlassCard title="相关性热力图">
        {selectedCodes.length < 2 ? (
          <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-secondary)' }}>
            请至少选择2只标的进行分析
          </div>
        ) : isLoading ? (
          <Spin size="large" style={{ display: 'block', margin: 'var(--space-8) auto' }} />
        ) : correlationData ? (
          <CorrelationHeatmap codes={correlationData.codes} matrix={correlationData.matrix} />
        ) : null}
      </GlassCard>
    </div>
  );
}
