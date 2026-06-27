import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useIsMobile } from '@/hooks/useBreakpoint';

interface CorrelationHeatmapProps {
  codes: string[];
  matrix: number[][];
}

export default function CorrelationHeatmap({ codes, matrix }: CorrelationHeatmapProps) {
  const isMobile = useIsMobile();
  const data: [number, number, number][] = [];
  matrix.forEach((row, i) => {
    row.forEach((val, j) => {
      data.push([i, j, parseFloat(val.toFixed(2))]);
    });
  });

  const labelFontSize = isMobile ? 8 : 10;

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'var(--font-sans)' },
    tooltip: {
      position: 'top',
      backgroundColor: 'var(--bg-elevated)',
      borderColor: 'var(--border-default)',
      textStyle: { color: 'var(--text-primary)' },
      formatter: (params: any) => {
        const i = params.data[0];
        const j = params.data[1];
        const v = params.data[2];
        return `${codes[i]} vs ${codes[j]}: ${v}`;
      },
    },
    grid: {
      top: 40,
      bottom: isMobile ? 50 : 60,
      left: isMobile ? 45 : 60,
      right: 20,
      borderColor: 'var(--border-default)',
    },
    xAxis: {
      type: 'category',
      data: codes,
      splitArea: { show: true, areaStyle: { color: ['rgba(255,255,255,0.02)', 'rgba(255,255,255,0.04)'] } },
      axisLabel: { rotate: 45, fontSize: labelFontSize, color: 'var(--text-secondary)' },
      axisLine: { lineStyle: { color: 'var(--text-tertiary)' } },
      axisTick: { lineStyle: { color: 'var(--text-tertiary)' } },
      splitLine: { lineStyle: { color: 'var(--border-default)' } },
    },
    yAxis: {
      type: 'category',
      data: codes,
      splitArea: { show: true, areaStyle: { color: ['rgba(255,255,255,0.02)', 'rgba(255,255,255,0.04)'] } },
      axisLabel: { fontSize: labelFontSize, color: 'var(--text-secondary)' },
      axisLine: { lineStyle: { color: 'var(--text-tertiary)' } },
      axisTick: { lineStyle: { color: 'var(--text-tertiary)' } },
      splitLine: { lineStyle: { color: 'var(--border-default)' } },
    },
    visualMap: {
      min: -1,
      max: 1,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      textStyle: { color: 'var(--text-secondary)', fontSize: isMobile ? 10 : 12 },
      inRange: { color: ['#22c55e', '#0a0a0a', '#ef4444'] },
    },
    series: [{
      type: 'heatmap',
      data,
      label: { show: true, fontSize: labelFontSize, color: 'var(--text-primary)' },
      emphasis: { itemStyle: { shadowBlur: 0 } },
    }],
  };

  return <ReactECharts option={option} style={{ height: isMobile ? 300 : 400 }} />;
}
