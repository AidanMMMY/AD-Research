import { useEffect, useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { resolveChartColors } from '@/utils/cssVar';
import { subscribeChartThemeCache } from '@/utils/chartColors';
import { useSettingsStore } from '@/stores/settings';

interface CorrelationHeatmapProps {
  codes: string[];
  matrix: number[][];
}

export default function CorrelationHeatmap({ codes, matrix }: CorrelationHeatmapProps) {
  const isMobile = useIsMobile();
  const colorConvention = useSettingsStore((s) => s.colorConvention);
  const [themeTick, setThemeTick] = useState(0);
  useEffect(
    () => subscribeChartThemeCache(() => setThemeTick((t) => t + 1)),
    [],
  );

  const data: [number, number, number][] = [];
  matrix.forEach((row, i) => {
    row.forEach((val, j) => {
      data.push([i, j, parseFloat(val.toFixed(2))]);
    });
  });

  const labelFontSize = isMobile ? 8 : 10;

  // Resolve all CSS-variable colors at render time. Fallbacks mirror the
  // light-theme defaults in theme.css so SSR / no-DOM still renders correctly.
  const bgElevated = useMemo(
    () => resolveChartColors(['var(--bg-elevated)'], ['#F3F5F7'])[0],
    [themeTick, colorConvention],
  );
  const textPrimary = useMemo(
    () => resolveChartColors(['var(--text-primary)'], ['#0F1115'])[0],
    [themeTick, colorConvention],
  );
  const textSecondary = useMemo(
    () => resolveChartColors(['var(--text-secondary)'], ['#5B6778'])[0],
    [themeTick, colorConvention],
  );
  const textTertiary = useMemo(
    () => resolveChartColors(['var(--text-tertiary)'], ['#8894A4'])[0],
    [themeTick, colorConvention],
  );
  const borderDefault = useMemo(
    () => resolveChartColors(['var(--border-default)'], ['#e5e7eb'])[0],
    [themeTick, colorConvention],
  );

  // The splitArea checkerboard uses the elevated background tone; we derive
  // it from --bg-elevated so it follows the active palette automatically.
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
      bottom: isMobile ? 75 : 95,
      left: isMobile ? 50 : 70,
      right: 20,
      borderColor: borderDefault,
    },
    xAxis: {
      type: 'category',
      data: codes,
      splitArea: { show: true, areaStyle: { color: splitAreaColors } },
      axisLabel: {
        rotate: isMobile ? 45 : 30,
        fontSize: labelFontSize,
        color: textSecondary,
        interval: 0,
        formatter: (value: string) => value.length > 10 ? `${value.slice(0, 10)}...` : value,
      },
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
      // dataviz P0-2: correlation is a statistical measure, NOT a return,
      // so the rise/fall color convention doesn't apply. Use a fixed
      // diverging blue→gray→red gradient: cool blue for negative
      // correlation, neutral gray for zero, warm red for positive.
      // Literal hex (no CSS vars) — visualMap gradients look the same
      // in light & dark themes and aren't tied to market semantics.
      inRange: { color: ['#3b82f6', '#9ca3af', '#ef4444'] },
    },
    series: [{
      type: 'heatmap',
      data,
      label: { show: true, fontSize: labelFontSize, color: textPrimary },
      emphasis: { itemStyle: { shadowBlur: 0 } },
    }],
  };

  return <ReactECharts option={option} style={{ height: '100%' }} />;
}