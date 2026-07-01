import { useEffect, useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { resolveChartColors } from '@/utils/cssVar';

interface CorrelationHeatmapProps {
  codes: string[];
  matrix: number[][];
}

export default function CorrelationHeatmap({ codes, matrix }: CorrelationHeatmapProps) {
  const isMobile = useIsMobile();
  const [, setThemeTick] = useState(0);
  useEffect(() => {
    const handler = () => setThemeTick((t) => t + 1);
    document.addEventListener('themechange', handler);
    return () => document.removeEventListener('themechange', handler);
  }, []);

  const data: [number, number, number][] = [];
  matrix.forEach((row, i) => {
    row.forEach((val, j) => {
      data.push([i, j, parseFloat(val.toFixed(2))]);
    });
  });

  const labelFontSize = isMobile ? 8 : 10;

  // Resolve all CSS-variable colors at render time. Fallbacks are the
  // terminal-theme defaults so SSR / no-DOM still renders correctly.
  const bgElevated = useMemo(
    () => resolveChartColors(['var(--bg-elevated)'], ['#111111'])[0],
    [],
  );
  const bgBase = useMemo(
    () => resolveChartColors(['var(--bg-base)'], ['#0a0a0a'])[0],
    [],
  );
  const colorFall = useMemo(
    () => resolveChartColors(['var(--color-fall)'], ['#5fa87a'])[0],
    [],
  );
  const colorRise = useMemo(
    () => resolveChartColors(['var(--color-rise)'], ['#c96b6b'])[0],
    [],
  );
  const textPrimary = useMemo(
    () => resolveChartColors(['var(--text-primary)'], ['#f5f5f0'])[0],
    [],
  );
  const textSecondary = useMemo(
    () => resolveChartColors(['var(--text-secondary)'], ['#888888'])[0],
    [],
  );
  const textTertiary = useMemo(
    () => resolveChartColors(['var(--text-tertiary)'], ['#444444'])[0],
    [],
  );
  const borderDefault = useMemo(
    () => resolveChartColors(['var(--border-default)'], ['rgba(255,255,255,0.06)'])[0],
    [],
  );

  // The splitArea checkerboard uses the elevated background tone; in
  // terminal it's a faint white overlay, in print a faint dark overlay on
  // cream. We derive it from --bg-elevated via alpha so it follows the
  // active palette automatically.
  const splitAreaColors = useMemo(() => {
    const base = bgElevated;
    return [base, base];
  }, [bgElevated]);

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'var(--font-sans)' },
    tooltip: {
      position: 'top',
      backgroundColor: bgElevated,
      borderColor: borderDefault,
      textStyle: { color: textPrimary },
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
      borderColor: borderDefault,
    },
    xAxis: {
      type: 'category',
      data: codes,
      splitArea: { show: true, areaStyle: { color: splitAreaColors } },
      axisLabel: { rotate: 45, fontSize: labelFontSize, color: textSecondary },
      axisLine: { lineStyle: { color: textTertiary } },
      axisTick: { lineStyle: { color: textTertiary } },
      splitLine: { lineStyle: { color: borderDefault } },
    },
    yAxis: {
      type: 'category',
      data: codes,
      splitArea: { show: true, areaStyle: { color: splitAreaColors } },
      axisLabel: { fontSize: labelFontSize, color: textSecondary },
      axisLine: { lineStyle: { color: textTertiary } },
      axisTick: { lineStyle: { color: textTertiary } },
      splitLine: { lineStyle: { color: borderDefault } },
    },
    visualMap: {
      min: -1,
      max: 1,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      textStyle: { color: textSecondary, fontSize: isMobile ? 10 : 12 },
      inRange: { color: [colorFall, bgBase, colorRise] },
    },
    series: [{
      type: 'heatmap',
      data,
      label: { show: true, fontSize: labelFontSize, color: textPrimary },
      emphasis: { itemStyle: { shadowBlur: 0 } },
    }],
  };

  return <ReactECharts option={option} style={{ height: isMobile ? 300 : 400 }} />;
}