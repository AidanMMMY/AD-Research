import { useEffect, useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react/lib/core';
import echarts from '@/utils/echarts';
import type { EChartsOption } from 'echarts';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { resolveChartColor, subscribeChartThemeCache } from '@/utils/chartColors';
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

  // Resolve all CSS-variable colors at render time via the single chart
  // color resolver (chartColors.ts, bare token names). Its built-in
  // fallbacks mirror the dark-theme defaults in theme.css (the default
  // theme) so SSR / no-DOM still renders correctly.
  const bgElevated = useMemo(
    () => resolveChartColor('--bg-elevated'),
    [themeTick, colorConvention],
  );
  const textPrimary = useMemo(
    () => resolveChartColor('--text-primary'),
    [themeTick, colorConvention],
  );
  const textSecondary = useMemo(
    () => resolveChartColor('--text-secondary'),
    [themeTick, colorConvention],
  );
  const textTertiary = useMemo(
    () => resolveChartColor('--text-tertiary'),
    [themeTick, colorConvention],
  );
  const borderDefault = useMemo(
    () => resolveChartColor('--border-default'),
    [themeTick, colorConvention],
  );

  // The splitArea checkerboard uses the elevated background tone; we derive
  // it from --bg-elevated so it follows the active palette automatically.
  const splitAreaColors = useMemo(() => {
    const base = bgElevated;
    return [base, base];
  }, [bgElevated]);

  // 设计系统波 1（原 dataviz P0-2 修正）：inRange 曾用绕过 token 的红蓝
  // 字面量，且在红涨绿跌约定下语义颠倒（正相关显示冷蓝）。相关性虽不是
  // 收益，但「正/负」语义应与全站涨跌色约定一致：正相关用 --color-rise、
  // 负相关用 --color-fall、零相关用 --color-neutral，通过统一解析器读取，
  // 跟随主题与 data-color-convention 切换（中国约定：正相关 = 红）。
  const inRangeColors = useMemo(
    () => [
      resolveChartColor('--color-fall'),
      resolveChartColor('--color-neutral'),
      resolveChartColor('--color-rise'),
    ],
    [themeTick, colorConvention],
  );

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
      // 负相关 → 零 → 正相关：跌色 / 中性色 / 涨色（见上方注释）。
      inRange: { color: inRangeColors },
    },
    series: [{
      type: 'heatmap',
      data,
      label: { show: true, fontSize: labelFontSize, color: textPrimary },
      emphasis: { itemStyle: { shadowBlur: 0 } },
    }],
  };

  return <ReactECharts echarts={echarts} option={option} style={{ height: '100%' }} role="img" aria-label="相关性热力图" />;
}