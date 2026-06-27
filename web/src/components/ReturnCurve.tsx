import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useIsMobile } from '@/hooks/useBreakpoint';

interface SeriesData {
  name: string;
  dates: string[];
  values: number[];
}

interface ReturnCurveProps {
  series: SeriesData[];
}

export default function ReturnCurve({ series }: ReturnCurveProps) {
  const isMobile = useIsMobile();

  const allDates = series[0]?.dates || [];
  // On mobile, show fewer x-axis labels
  const labelInterval = isMobile ? Math.max(1, Math.floor(allDates.length / 6)) : 0;

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'var(--font-sans)' },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'var(--bg-elevated)',
      borderColor: 'var(--border-default)',
      textStyle: { color: 'var(--text-primary)' },
    },
    legend: {
      top: 0,
      textStyle: { color: 'var(--text-secondary)', fontSize: isMobile ? 11 : 12 },
      pageTextStyle: { color: 'var(--text-secondary)' },
    },
    grid: { left: isMobile ? 45 : 50, right: 20, top: 40, bottom: 30, borderColor: 'var(--border-default)' },
    xAxis: {
      type: 'category',
      data: allDates,
      axisLabel: {
        fontSize: isMobile ? 9 : 10,
        color: 'var(--text-secondary)',
        interval: labelInterval,
      },
      axisLine: { lineStyle: { color: 'var(--text-tertiary)' } },
      axisTick: { lineStyle: { color: 'var(--text-tertiary)' } },
      splitLine: { show: true, lineStyle: { color: 'var(--border-default)' } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: '{value}%', fontSize: isMobile ? 9 : 10, color: 'var(--text-secondary)' },
      axisLine: { lineStyle: { color: 'var(--text-tertiary)' } },
      axisTick: { lineStyle: { color: 'var(--text-tertiary)' } },
      splitLine: { show: true, lineStyle: { color: 'var(--border-default)' } },
    },
    series: series.map((s, idx) => ({
      name: s.name,
      type: 'line',
      data: s.values,
      smooth: true,
      symbol: 'none',
      lineStyle: {
        width: 2,
      },
      itemStyle: {
        color: ['#22d3ee', '#555555', '#22c55e', '#ef4444', '#eab308'][idx % 5],
      },
    })),
  };

  return <ReactECharts option={option} style={{ height: isMobile ? 240 : 320 }} />;
}
