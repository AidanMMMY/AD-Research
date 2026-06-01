import { useState } from 'react';
import { Card, Row, Col, Select, Button, Tag, Space, Spin, message } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { analysisApi } from '@/api/analysis';
import { useETFList } from '@/hooks/useETFList';
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

const PRESET_GROUPS = [
  { label: '宽基', codes: ['510300', '510050', '510500', '159915'] },
  { label: '科技', codes: ['512480', '515030', '159819', '159995'] },
  { label: '消费', codes: ['159928', '512690', '515650', '159996'] },
  { label: '医药', codes: ['512010', '512170', '159992', '159938'] },
];

export default function CorrelationAnalysis() {
  const [selectedCodes, setSelectedCodes] = useState<string[]>(['510300', '510050', '510500', '159915']);
  const [window, setWindow] = useState<number>(60);
  const [method, setMethod] = useState<'pearson' | 'spearman'>('pearson');

  const { data: etfList } = useETFList({ page_size: 200 });

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

  const handleAddPreset = (codes: string[]) => {
    const newCodes = Array.from(new Set([...selectedCodes, ...codes]));
    if (newCodes.length > 20) {
      message.warning('最多选择20只ETF');
      return;
    }
    setSelectedCodes(newCodes);
  };

  const handleRemoveCode = (code: string) => {
    setSelectedCodes(selectedCodes.filter((c) => c !== code));
  };

  return (
    <div>
      <Card title="相关性分析配置" style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]}>
          <Col xs={24} md={12}>
            <div style={{ marginBottom: 8 }}>选择ETF（{selectedCodes.length}/20）：</div>
            <Select
              mode="multiple"
              showSearch
              placeholder="搜索并选择ETF"
              value={selectedCodes}
              onChange={setSelectedCodes}
              options={etfOptions}
              style={{ width: '100%' }}
              maxTagCount={5}
              filterOption={(input, option) =>
                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
            />
            <div style={{ marginTop: 8 }}>
              <Space size={[8, 8]} wrap>
                {selectedCodes.map((code) => (
                  <Tag key={code} closable onClose={() => handleRemoveCode(code)}>
                    {code}
                  </Tag>
                ))}
              </Space>
            </div>
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
        <Row style={{ marginTop: 12 }}>
          <Col span={24}>
            <Space>
              <span>快速选择：</span>
              {PRESET_GROUPS.map((group) => (
                <Button key={group.label} size="small" onClick={() => handleAddPreset(group.codes)}>
                  +{group.label}
                </Button>
              ))}
              <Button size="small" danger onClick={() => setSelectedCodes([])}>
                清空
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      <Card title="相关性热力图">
        {selectedCodes.length < 2 ? (
          <div style={{ textAlign: 'center', padding: 60, color: '#999' }}>
            请至少选择2只ETF进行分析
          </div>
        ) : isLoading ? (
          <Spin size="large" style={{ display: 'block', margin: '60px auto' }} />
        ) : correlationData ? (
          <CorrelationHeatmap codes={correlationData.codes} matrix={correlationData.matrix} />
        ) : null}
      </Card>
    </div>
  );
}
