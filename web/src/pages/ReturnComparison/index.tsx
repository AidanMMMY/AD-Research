import { useMemo, useState } from 'react';
import { Row, Col, Radio, Spin } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { marketApi } from '@/api/market';
import { useInstrumentList } from '@/hooks/useInstrumentList';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import FilterToolbar from '@/components/FilterToolbar';
import EmptyState from '@/components/EmptyState';
import InstrumentSelector from '@/components/InstrumentSelector';
import ReturnCurve from '@/components/ReturnCurve';
import HelpPopover from '@/components/HelpPopover';
import { useSettingsStore } from '@/stores/settings';

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
  const settingsMode = useSettingsStore((s) => s.mode);
  const [selectedCodes, setSelectedCodes] = useState<string[]>([]);
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

  const visibleSeries = series.filter((s) => s.dates.length > 0);

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        title="收益对比"
        description="对比多只标的的历史收益曲线，支持归一化和日收益率两种模式"
      />
      <Panel title="收益曲线对比配置" variant="default">
        <FilterToolbar>
          <Row gutter={[16, 16]}>
            <Col xs={24} md={12}>
              <InstrumentSelector
                value={selectedCodes}
                onChange={setSelectedCodes}
                maxCount={10}
              />
            </Col>
            <Col xs={24} md={6}>
              <div className="ad-filter-label">时间范围：</div>
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
              <div className="ad-filter-label">显示模式：</div>
              <Radio.Group
                value={mode}
                onChange={(e) => setMode(e.target.value)}
                optionType="button"
                buttonStyle="solid"
              >
                <Radio.Button value="normalized">
                  <HelpPopover termKey="normalized_return" mode={settingsMode}>归一化</HelpPopover>
                </Radio.Button>
                <Radio.Button value="percentage">
                  <HelpPopover termKey="daily_return" mode={settingsMode}>日收益</HelpPopover>
                </Radio.Button>
              </Radio.Group>
            </Col>
          </Row>
        </FilterToolbar>
      </Panel>

      <Panel title={mode === 'normalized' ? '归一化收益曲线' : '日收益率'} variant="default">
        {selectedCodes.length < 1 ? (
          <EmptyState
            title="请选择标的"
            description="请至少选择1只标的"
          />
        ) : etfQueries.isLoading ? (
          <Spin size="large" className="ad-spin-center" />
        ) : visibleSeries.length > 0 ? (
          <div className="ad-chart-container">
            <ReturnCurve series={visibleSeries} />
          </div>
        ) : (
          <EmptyState
            title="暂无数据"
            description="所选标的暂无历史行情数据"
          />
        )}
      </Panel>
    </PageShell>
  );
}
