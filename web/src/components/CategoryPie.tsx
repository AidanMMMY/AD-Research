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
    tooltip: {
      trigger: 'item',
      backgroundColor: '#0f1729',
      borderColor: 'rgba(255,255,255,0.08)',
      textStyle: { color: '#f1f5f9' },
    },
    legend: {
      bottom: 0,
      type: 'scroll',
      textStyle: { color: '#94a3b8', fontSize: isMobile ? 10 : 12 },
      pageTextStyle: { color: '#94a3b8' },
    },
    series: [{
      type: 'pie',
      radius: isMobile ? ['30%', '60%'] : ['40%', '70%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 8, borderColor: '#0f1729', borderWidth: 2 },
      label: { show: false, color: '#94a3b8' },
      emphasis: {
        label: { show: true, fontSize: 14, fontWeight: 'bold', color: '#f1f5f9' },
        itemStyle: {
          shadowBlur: 10,
          shadowColor: 'rgba(0,0,0,0.5)',
        },
      },
      data: pieData,
    }],
  };

  return <ReactECharts option={option} style={{ height: isMobile ? 220 : 280 }} />;
}
