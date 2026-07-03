import { useState } from 'react';
import { Row, Col, Select, Spin } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { analysisApi } from '@/api/analysis';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import FilterToolbar from '@/components/FilterToolbar';
import EmptyState from '@/components/EmptyState';
import InstrumentSelector from '@/components/InstrumentSelector';
import CorrelationHeatmap from '@/components/CorrelationHeatmap';
import HelpPopover from '@/components/HelpPopover';
import { useSettingsStore } from '@/stores/settings';

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
  const mode = useSettingsStore((s) => s.mode);
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
    <PageShell maxWidth="wide">
      <PageHeader
        title="相关性分析"
        description="分析多只标的之间的价格相关性，支持多种计算方法和时间窗口"
      />
      <Panel title="相关性分析配置" variant="default">
        <FilterToolbar>
          <Row gutter={[16, 16]}>
            <Col xs={24} md={12}>
              <InstrumentSelector
                value={selectedCodes}
                onChange={setSelectedCodes}
                maxCount={20}
              />
            </Col>
            <Col xs={24} md={6}>
              <div className="ad-filter-label">
                <HelpPopover termKey="time_range" mode={mode}>窗口期</HelpPopover>：
              </div>
              <Select
                value={window}
                onChange={setWindow}
                options={WINDOW_OPTIONS}
                style={{ width: '100%' }}
              />
            </Col>
            <Col xs={24} md={6}>
              <div className="ad-filter-label">
                <HelpPopover termKey="correlation_method" mode={mode}>计算方法</HelpPopover>：
              </div>
              <Select
                value={method}
                onChange={setMethod}
                options={METHOD_OPTIONS.map((opt) => ({
                  ...opt,
                  label: (
                    <HelpPopover termKey={opt.value === 'pearson' ? 'pearson' : 'spearman'} mode={mode}>
                      {opt.label}
                    </HelpPopover>
                  ),
                }))}
                style={{ width: '100%' }}
              />
            </Col>
          </Row>
        </FilterToolbar>
      </Panel>

      <Panel title="相关性热力图" variant="default">
        {selectedCodes.length < 2 ? (
          <EmptyState
            title="请选择标的"
            description="请至少选择2只标的进行分析"
          />
        ) : isLoading ? (
          <Spin size="large" className="ad-spin-center" />
        ) : correlationData ? (
          <div className="ad-chart-container">
            <CorrelationHeatmap codes={correlationData.codes} matrix={correlationData.matrix} />
          </div>
        ) : null}
      </Panel>
    </PageShell>
  );
}
