import { useMemo, useState } from 'react';
import { Row, Col, Select, Radio, Button, Space, Spin, message } from 'antd';
import { FolderOpenOutlined } from '@ant-design/icons';
import GlassCard from '@/components/GlassCard';
import ThemeTag from '@/components/ThemeTag';
import { useQuery } from '@tanstack/react-query';
import { marketApi } from '@/api/market';
import { useETFList } from '@/hooks/useETFList';
import { usePoolList } from '@/hooks/usePoolDetail';
import ReturnCurve from '@/components/ReturnCurve';

const TIME_RANGE_OPTIONS = [
  { label: '1月', value: 30 },
  { label: '3月', value: 90 },
  { label: '6月', value: 180 },
  { label: '1年', value: 252 },
  { label: '全部', value: 0 },
];

const PRESET_TOP_N = 4;

interface ETFItem {
  code: string;
  name: string;
  category?: string;
  fund_size?: number;
}

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

  const poolOptions = (pools || []).map((pool) => ({
    label: `${pool.name} (${pool.members?.length || 0}只)`,
    value: pool.id,
    codes: (pool.members || []).map((m) => m.etf_code),
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
      message.warning('最多选择10只标的');
      return;
    }
    setSelectedCodes(newCodes);
  };

  const handleSelectPool = (poolId: number | undefined) => {
    if (!poolId) return;
    const pool = poolOptions.find((p) => p.value === poolId);
    if (!pool) return;
    const newCodes = Array.from(new Set([...selectedCodes, ...pool.codes]));
    if (newCodes.length > 10) {
      message.warning('标的池成员数量较多，仅添加前10只');
      setSelectedCodes(newCodes.slice(0, 10));
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
      <h1 style={{ fontSize: 'var(--text-h1-size)', fontWeight: 500, color: 'var(--text-primary)', margin: '0 0 8px', letterSpacing: '-0.03em' }}>收益对比</h1>
      <p style={{ margin: '0 0 32px', color: 'var(--text-tertiary)', fontSize: 'var(--text-body-size)' }}>对比多只标的的历史收益曲线，支持归一化和日收益率两种模式</p>
      <GlassCard title="收益曲线对比配置" style={{ marginBottom: 'var(--space-4)' }}>
        <Row gutter={[16, 16]}>
          <Col xs={24} md={12}>
            <div style={{ marginBottom: 8 }}>选择标的（{selectedCodes.length}/10）：</div>
            <Select
              mode="multiple"
              showSearch
              placeholder="搜索并选择标的"
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
                  <ThemeTag key={code} variant="accent" style={{ cursor: 'default' }}>
                    {code}
                    <span style={{ marginLeft: 4, cursor: 'pointer' }} onClick={() => handleRemoveCode(code)}>×</span>
                  </ThemeTag>
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
          </Col>
        </Row>
      </GlassCard>

      <GlassCard title={mode === 'normalized' ? '归一化收益曲线' : '日收益率'}>
        {selectedCodes.length < 1 ? (
          <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-secondary)' }}>
            请至少选择1只标的
          </div>
        ) : etfQueries.isLoading ? (
          <Spin size="large" style={{ display: 'block', margin: '60px auto' }} />
        ) : series.length > 0 ? (
          <ReturnCurve series={series} />
        ) : null}
      </GlassCard>
    </div>
  );
}
