import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useIsMobile } from '@/hooks/useBreakpoint';

interface ScoreRadarProps {
  data: {
    score_return: number;
    score_risk: number;
    score_sharpe: number;
    score_liquidity: number;
    score_trend: number;
  };
}

export default function ScoreRadar({ data }: ScoreRadarProps) {
  const isMobile = useIsMobile();

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'var(--font-sans)' },
    radar: {
      indicator: [
        { name: '收益能力', max: 100 },
        { name: '风险控制', max: 100 },
        { name: '夏普比率', max: 100 },
        { name: '流动性', max: 100 },
        { name: '趋势强度', max: 100 },
      ],
      radius: isMobile ? '55%' : '65%',
      axisName: {
        color: 'var(--text-secondary)',
        fontSize: isMobile ? 10 : 12,
      },
      splitArea: {
        areaStyle: {
          color: ['var(--accent-dim)', 'var(--text-tertiary)', 'var(--accent-dim)', 'var(--text-tertiary)'],
        },
      },
      splitLine: {
        lineStyle: {
          color: 'var(--border-default)',
        },
      },
      axisLine: {
        lineStyle: {
          color: 'var(--border-default)',
        },
      },
    },
    series: [{
      type: 'radar',
      data: [{
        value: [
          data.score_return,
          data.score_risk,
          data.score_sharpe,
          data.score_liquidity,
          data.score_trend,
        ],
        name: '评分',
        areaStyle: { opacity: 0.3, color: 'var(--accent)' },
        lineStyle: { color: 'var(--accent)', width: 2 },
        itemStyle: { color: 'var(--accent)' },
      }],
    }],
    tooltip: {
      trigger: 'item',
      backgroundColor: 'var(--bg-elevated)',
      borderColor: 'var(--border-default)',
      textStyle: { color: 'var(--text-primary)' },
    },
  };

  return <ReactECharts option={option} style={{ height: isMobile ? 240 : 300 }} />;
}
