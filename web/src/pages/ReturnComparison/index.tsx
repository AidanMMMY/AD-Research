import { useState, useMemo } from 'react';
import { Card, Row, Col, Select, Radio, Button, Tag, Space, Spin, message } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { marketApi } from '@/api/market';
import { useETFList } from '@/hooks/useETFList';
import ReturnCurve from '@/components/ReturnCurve';

const TIME_RANGE_OPTIONS = [
  { label: '1月', value: 30 },
  { label: '3月', value: 90 },
  { label: '6月', value: 180 },
  { label: '1年', value: 252 },
  { label: '全部', value: 0 },
];

const PRESET_GROUPS = [
  { label: '宽基', codes: ['510300', '510050', '510500', '159915'] },
  { label: '科技', codes: ['512480', '515030', '159819', '159995'] },
  { label: '消费', codes: ['159928', '512690', '515650', '159996'] },
  { label: '医药', codes: ['512010', '512170', '159992', '159938'] },
];

interface SeriesData {
  name: string;
  dates: string[];
  values: number[];
}

export default function ReturnComparison() {
  const [selectedCodes, setSelectedCodes] = useState<string[]>(['510300', '510050', '510500']);
  const [timeRange, setTimeRange] = useState<number>(252);
  const [mode, setMode] = useState<'normalized' | 'percentage'>('normalized');

  const { data: etfList } = useETFList({ page_size: 200 });

  const etfQueries = useQuery({
    queryKey: ['return-comparison', selectedCodes, timeRange],
    queryFn: async () => {
      const results = await Promise.all(
        selectedCodes.map((code) =>
          marketApi.history(code, { limit: timeRange || 500 }).then((r) => ({
            code,
            items: r.data.items,
          }))
        )
      );
      return results;
    },
    enabled: selectedCodes.length >= 1,
    staleTime: 60_000,
  });

  const etfOptions = (etfList?.items || []).map((item) => ({
    label: `${item.code} ${item.name}`,
    value: item.code,
  }));

  const series: SeriesData[] = useMemo(() => {
    if (!etfQueries.data) return [];
    return etfQueries.data.map(({ code, items }) => {
      const etfName = etfList?.items.find((e) => e.code === code)?.name || code;
      if (mode === 'normalized') {
        const base = items[0]?.close || 1;
        return {
          name: `${code} ${etfName}`,
          dates: items.map((d) => d.trade_date),
          values: items.map((d) => ((d.close - base) / base) * 100),
        };
      } else {
        const dailyReturns: number[] = [];
        const dates: string[] = [];
        for (let i = 1; i < items.length; i++) {
          const ret = ((items[i].close - items[i - 1].close) / items[i - 1].close) * 100;
          dailyReturns.push(ret);
          dates.push(items[i].trade_date);
        }
        return {
          name: `${code} ${etfName}`,
          dates,
          values: dailyReturns,
        };
      }
    });
  }, [etfQueries.data, mode, etfList]);

  const handleAddPreset = (codes: string[]) => {
    const newCodes = Array.from(new Set([...selectedCodes, ...codes]));
    if (newCodes.length > 10) {
      message.warning('最多选择10只ETF');
      return;
    }
    setSelectedCodes(newCodes);
  };

  const handleRemoveCode = (code: string) => {
    setSelectedCodes(selectedCodes.filter((c) => c !== code));
  };

  return (
    <div>
      <Card title="收益曲线对比配置" style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]}>
          <Col xs={24} md={12}>
            <div style={{ marginBottom: 8 }}>选择ETF（{selectedCodes.length}/10）：</div>
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
            <div style={{ marginBottom: 8 }}>时间范围：</div>
            <Radio.Group
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value)}
              optionType="button"
              buttonStyle="solid"
            >
              {TIME_RANGE_OPTIONS.map((opt) => (
                <Radio.Button key={opt.value} value={opt.value}>
                  {opt.label}
                </Radio.Button>
              ))}
            </Radio.Group>
          </Col>
          <Col xs={24} md={6}>
            <div style={{ marginBottom: 8 }}>显示模式：</div>
            <Radio.Group
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              optionType="button"
              buttonStyle="solid"
            >
              <Radio.Button value="normalized">归一化</Radio.Button>
              <Radio.Button value="percentage">日收益</Radio.Button>
            </Radio.Group>
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

      <Card title={mode === 'normalized' ? '归一化收益曲线' : '日收益率'}>
        {selectedCodes.length < 1 ? (
          <div style={{ textAlign: 'center', padding: 60, color: '#999' }}>
            请至少选择1只ETF
          </div>
        ) : etfQueries.isLoading ? (
          <Spin size="large" style={{ display: 'block', margin: '60px auto' }} />
        ) : series.length > 0 ? (
          <ReturnCurve series={series} />
        ) : null}
      </Card>
    </div>
  );
}
