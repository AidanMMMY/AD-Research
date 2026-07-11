import { useEffect, useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { resolveChartColors } from '@/utils/cssVar';

interface SeriesData {
  name: string;
  dates: string[];
  values: number[];
}

interface ReturnCurveProps {
  series: SeriesData[];
}

/**
 * Return-curve chart. Echarts cannot resolve `var(--xxx)` strings, so all
 * CSS-variable references are resolved via getComputedStyle at render time.
 * The component re-resolves on theme changes because the `option` object
 * is regenerated whenever `useIsMobile` or the data series change, and
 * ReactECharts' internal listener responds to the `themechange` event
 * by re-rendering its host component on the next data update.
 */
export default function ReturnCurve({ series }: ReturnCurveProps) {
  const isMobile = useIsMobile();
  // Bump when the active theme changes so memoized CSS-var lookups
  // re-run and the echarts instance repaints in the new palette.
  const [themeTick, setThemeTick] = useState(0);

  useEffect(() => {
    const handler = () => setThemeTick((t) => t + 1);
    document.addEventListener('themechange', handler);
    return () => document.removeEventListener('themechange', handler);
  }, []);

  const allDates = series[0]?.dates || [];
  // Keep x-axis labels readable: target ~8 labels across the chart
  const labelInterval = Math.max(0, Math.floor(allDates.length / 8));

  // Resolve the categorical series palette once per render. We provide 10
  // distinct hues so up to 10 compared instruments do not share a color.
  // `themeTick` is bumped on theme changes so the resolved values repaint.
  const palette = useMemo(
    () =>
      resolveChartColors(
        Array.from({ length: 10 }, (_, i) => `var(--chart-series-${i + 1})`),
        [
          '#0072B2', '#E69F00', '#009E73', '#CC79A7', '#56B4E9',
          '#F0E442', '#D55E00', '#000000', '#4f46e5', '#65a30d',
        ],
      ),
    [themeTick],
  );
  const bgElevated = useMemo(
    () => resolveChartColors(['var(--bg-elevated)'], ['#F3F5F7']),
    [],
  );
  const borderDefault = useMemo(
    () => resolveChartColors(['var(--border-default)'], ['#e5e7eb']),
    [],
  );
  const textPrimary = useMemo(
    () => resolveChartColors(['var(--text-primary)'], ['#0F1115']),
    [],
  );
  const textSecondary = useMemo(
    () => resolveChartColors(['var(--text-secondary)'], ['#5B6778']),
    [],
  );
  const textTertiary = useMemo(
    () => resolveChartColors(['var(--text-tertiary)'], ['#8894A4']),
    [],
  );

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'var(--font-sans)' },
    tooltip: {
      trigger: 'axis',
      backgroundColor: bgElevated[0],
      borderColor: borderDefault[0],
      textStyle: { color: textPrimary[0] },
    },
    legend: {
      top: 0,
      textStyle: { color: textSecondary[0], fontSize: isMobile ? 11 : 12 },
      pageTextStyle: { color: textSecondary[0] },
    },
    grid: { left: isMobile ? 45 : 50, right: 20, top: 40, bottom: 30, borderColor: borderDefault[0] },
    xAxis: {
      type: 'category',
      data: allDates,
      axisLabel: {
        fontSize: isMobile ? 9 : 10,
        color: textSecondary[0],
        interval: labelInterval,
      },
      axisLine: { lineStyle: { color: textTertiary[0] } },
      axisTick: { lineStyle: { color: textTertiary[0] } },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: '{value}%', fontSize: isMobile ? 9 : 10, color: textSecondary[0] },
      axisLine: { lineStyle: { color: textTertiary[0] } },
      axisTick: { lineStyle: { color: textTertiary[0] } },
      splitLine: { show: true, lineStyle: { color: borderDefault[0], type: 'dashed', opacity: 0.5 } },
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
        color: palette[idx % palette.length],
      },
    })),
  };

  return <ReactECharts option={option} style={{ height: isMobile ? 240 : 320 }} />;
}