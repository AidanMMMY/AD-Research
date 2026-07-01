import { useMemo, useState } from 'react';
import { Row, Col, Radio, Spin } from 'antd';
import GlassCard from '@/components/GlassCard';
import { useQuery } from '@tanstack/react-query';
import { marketApi } from '@/api/market';
import { useInstrumentList } from '@/hooks/useInstrumentList';
import InstrumentSelector from '@/components/InstrumentSelector';
import ReturnCurve from '@/components/ReturnCurve';

const TIME_RANGE_OPTIONS = [
  { label: '1月', value: 30 },
  { label: '3月', value: 90 },
  { label: '6月', value: 180 },
  { label: '1年', value: 252 },
  { label: '全部', value: 0 },
];

interface SeriesData {
  name: string;
  dates: string[];
  values: number[];
}

export default function ReturnComparison() {
  const [selectedCodes, setSelectedCodes] = useState<string[]>(['510300.SH', '510050.SH', '510500.SH']);
  const [timeRange, setTimeRange] = useState<number>(252);
  const [mode, setMode] = useState<'normalized' | 'percentage'>('normalized');

  const { data: etfList } = useInstrumentList({ page_size: 10000 });

  const etfQueries = useQuery({
    queryKey: ['return-comparison', selectedCodes, timeRange],
    queryFn: async () => {
      const results = await Promise.all(
        selectedCodes.map((code) =>
          marketApi.history(code, { limit: timeRange || undefined }).then((r) => ({
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

  return (
    <div>
      <h1 style={{ fontSize: 'var(--text-h1-size)', fontWeight: 500, color: 'var(--text-primary)', margin: '0 0 8px', letterSpacing: '-0.03em' }}>收益对比</h1>
      <p style={{ margin: '0 0 32px', color: 'var(--text-tertiary)', fontSize: 'var(--text-body-size)' }}>对比多只标的的历史收益曲线，支持归一化和日收益率两种模式</p>
      <GlassCard title="收益曲线对比配置" style={{ marginBottom: 'var(--space-4)' }}>
        <Row gutter={[16, 16]}>
          <Col xs={24} md={12}>
            <InstrumentSelector
              value={selectedCodes}
              onChange={setSelectedCodes}
              maxCount={10}
            />
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
      </GlassCard>

      <GlassCard title={mode === 'normalized' ? '归一化收益曲线' : '日收益率'}>
        {selectedCodes.length < 1 ? (
          <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-secondary)' }}>
            请至少选择1只标的
          </div>
        ) : etfQueries.isLoading ? (
          <Spin size="large" style={{ display: 'block', margin: '60px auto' }} />
        ) : series.filter((s) => s.dates.length > 0).length > 0 ? (
          <ReturnCurve series={series.filter((s) => s.dates.length > 0)} />
        ) : (
          <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-secondary)' }}>
            所选标的暂无历史行情数据
          </div>
        )}
      </GlassCard>
    </div>
  );
}
