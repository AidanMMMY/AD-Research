import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';

interface SeriesData {
  name: string;
  dates: string[];
  values: number[];
}

interface ReturnCurveProps {
  series: SeriesData[];
}

export default function ReturnCurve({ series }: ReturnCurveProps) {
  const option: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#0f1729',
      borderColor: 'rgba(255,255,255,0.08)',
      textStyle: { color: '#f1f5f9' },
    },
    legend: {
      top: 0,
      textStyle: { color: '#94a3b8' },
      pageTextStyle: { color: '#94a3b8' },
    },
    grid: { left: 50, right: 20, top: 40, bottom: 30 },
    xAxis: {
      type: 'category',
      data: series[0]?.dates || [],
      axisLabel: { fontSize: 10, color: '#94a3b8' },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      axisTick: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      splitLine: { show: true, lineStyle: { color: 'rgba(255,255,255,0.06)' } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: '{value}%', fontSize: 10, color: '#94a3b8' },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      axisTick: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      splitLine: { show: true, lineStyle: { color: 'rgba(255,255,255,0.06)' } },
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
        color: ['#6366f1', '#06b6d4', '#22c55e', '#ef4444', '#eab308'][idx % 5],
      },
    })),
  };

  return <ReactECharts option={option} style={{ height: 320 }} />;
}
