import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';

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
  const option: EChartsOption = {
    backgroundColor: 'transparent',
    radar: {
      indicator: [
        { name: '收益能力', max: 100 },
        { name: '风险控制', max: 100 },
        { name: '夏普比率', max: 100 },
        { name: '流动性', max: 100 },
        { name: '趋势强度', max: 100 },
      ],
      radius: '65%',
      axisName: {
        color: '#94a3b8',
      },
      splitArea: {
        areaStyle: {
          color: ['rgba(99,102,241,0.05)', 'rgba(99,102,241,0.1)', 'rgba(99,102,241,0.05)', 'rgba(99,102,241,0.1)'],
        },
      },
      splitLine: {
        lineStyle: {
          color: 'rgba(255,255,255,0.06)',
        },
      },
      axisLine: {
        lineStyle: {
          color: 'rgba(255,255,255,0.06)',
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
        areaStyle: { opacity: 0.3, color: '#6366f1' },
        lineStyle: { color: '#6366f1', width: 2 },
        itemStyle: { color: '#6366f1' },
      }],
    }],
    tooltip: {
      trigger: 'item',
      backgroundColor: '#0f1729',
      borderColor: 'rgba(255,255,255,0.08)',
      textStyle: { color: '#f1f5f9' },
    },
  };

  return <ReactECharts option={option} style={{ height: 300 }} />;
}
