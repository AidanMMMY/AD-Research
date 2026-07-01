import { useEffect, useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { resolveChartColors } from '@/utils/cssVar';

interface CategoryPieProps {
  data: Record<string, { count: number; weight: number }>;
  mode?: 'count' | 'weight';
}

export default function CategoryPie({ data, mode = 'count' }: CategoryPieProps) {
  const isMobile = useIsMobile();
  const [, setThemeTick] = useState(0);
  useEffect(() => {
    const handler = () => setThemeTick((t) => t + 1);
    document.addEventListener('themechange', handler);
    return () => document.removeEventListener('themechange', handler);
  }, []);

  const entries = Object.entries(data);
  const pieData = entries.map(([name, val]) => ({
    name,
    value: mode === 'count' ? val.count : val.weight,
  }));

  // Resolve all CSS-variable colors once per render. Fallbacks are the
  // terminal-theme defaults so SSR / no-DOM still renders correctly.
  const palette = useMemo(
    () =>
      resolveChartColors(
        [
          'var(--accent)',
          'var(--color-rise)',
          'var(--color-fall)',
          'var(--text-tertiary)',
          'var(--text-secondary)',
          'var(--accent-dim)',
          'var(--color-rise-dim)',
          'var(--color-fall-dim)',
        ],
        ['#5fa87a', '#c96b6b', '#5fa87a', '#444444', '#888888', 'rgba(95,168,122,0.10)', 'rgba(201,107,107,0.12)', 'rgba(95,168,122,0.12)'],
      ),
    [],
  );
  const bgElevated = useMemo(
    () => resolveChartColors(['var(--bg-elevated)'], ['#111111']),
    [],
  );
  const borderDefault = useMemo(
    () => resolveChartColors(['var(--border-default)'], ['rgba(255,255,255,0.06)']),
    [],
  );
  const textPrimary = useMemo(
    () => resolveChartColors(['var(--text-primary)'], ['#f5f5f0']),
    [],
  );
  const textSecondary = useMemo(
    () => resolveChartColors(['var(--text-secondary)'], ['#888888']),
    [],
  );

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'var(--font-sans)' },
    tooltip: {
      trigger: 'item',
      backgroundColor: bgElevated[0],
      borderColor: borderDefault[0],
      textStyle: { color: textPrimary[0] },
    },
    legend: {
      bottom: 0,
      type: 'scroll',
      textStyle: { color: textSecondary[0], fontSize: isMobile ? 10 : 12 },
      pageTextStyle: { color: textSecondary[0] },
    },
    color: palette,
    series: [{
      type: 'pie',
      radius: isMobile ? ['30%', '60%'] : ['40%', '70%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 8, borderColor: bgElevated[0], borderWidth: 2 },
      label: { show: false, color: textSecondary[0] },
      emphasis: {
        label: { show: true, fontSize: 14, fontWeight: 'bold', color: textPrimary[0] },
      },
      data: pieData,
    }],
  };

  return <ReactECharts option={option} style={{ height: isMobile ? 220 : 280 }} />;
}