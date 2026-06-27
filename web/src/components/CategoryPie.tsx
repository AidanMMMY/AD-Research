import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useIsMobile } from '@/hooks/useBreakpoint';

interface CategoryPieProps {
  data: Record<string, { count: number; weight: number }>;
  mode?: 'count' | 'weight';
}

export default function CategoryPie({ data, mode = 'count' }: CategoryPieProps) {
  const isMobile = useIsMobile();
  const entries = Object.entries(data);
  const pieData = entries.map(([name, val]) => ({
    name,
    value: mode === 'count' ? val.count : val.weight,
  }));

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'var(--font-sans)' },
    tooltip: {
      trigger: 'item',
      backgroundColor: 'var(--bg-elevated)',
      borderColor: 'var(--border-default)',
      textStyle: { color: 'var(--text-primary)' },
    },
    legend: {
      bottom: 0,
      type: 'scroll',
      textStyle: { color: 'var(--text-secondary)', fontSize: isMobile ? 10 : 12 },
      pageTextStyle: { color: 'var(--text-secondary)' },
    },
    color: ['var(--accent)', 'var(--color-rise)', 'var(--color-fall)', 'var(--text-tertiary)', 'var(--text-secondary)', 'var(--accent-dim)', 'var(--color-rise-dim)', 'var(--color-fall-dim)'],
    series: [{
      type: 'pie',
      radius: isMobile ? ['30%', '60%'] : ['40%', '70%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 8, borderColor: 'var(--bg-elevated)', borderWidth: 2 },
      label: { show: false, color: 'var(--text-secondary)' },
      emphasis: {
        label: { show: true, fontSize: 14, fontWeight: 'bold', color: 'var(--text-primary)' },
      },
      data: pieData,
    }],
  };

  return <ReactECharts option={option} style={{ height: isMobile ? 220 : 280 }} />;
}
