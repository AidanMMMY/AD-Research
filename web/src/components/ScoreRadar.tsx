import { useEffect, useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react/lib/core';
import echarts from '@/utils/echarts';
import type { EChartsOption } from 'echarts';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { resolveChartColors } from '@/utils/chartColors';

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
  const [themeTick, setThemeTick] = useState(0);
  useEffect(() => {
    const handler = () => setThemeTick((t) => t + 1);
    document.addEventListener('themechange', handler);
    return () => document.removeEventListener('themechange', handler);
  }, []);

  const accent = useMemo(
    () => resolveChartColors(['--accent'], ['#2563EB'])[0],
    [themeTick],
  );
  const accentDim = useMemo(
    () => resolveChartColors(['--accent-dim'], ['rgba(37, 99, 235, 0.08)'])[0],
    [themeTick],
  );
  const textTertiary = useMemo(
    () => resolveChartColors(['--text-tertiary'], ['#8894A4'])[0],
    [themeTick],
  );
  const textSecondary = useMemo(
    () => resolveChartColors(['--text-secondary'], ['#5B6778'])[0],
    [themeTick],
  );
  const borderDefault = useMemo(
    () => resolveChartColors(['--border-default'], ['#e5e7eb'])[0],
    [themeTick],
  );
  const bgElevated = useMemo(
    () => resolveChartColors(['--bg-elevated'], ['#F3F5F7'])[0],
    [themeTick],
  );
  const textPrimary = useMemo(
    () => resolveChartColors(['--text-primary'], ['#0F1115'])[0],
    [themeTick],
  );

  const option: EChartsOption = {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: '--font-sans' },
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
        color: textSecondary,
        fontSize: isMobile ? 10 : 12,
      },
      splitArea: {
        areaStyle: {
          color: [accentDim, textTertiary, accentDim, textTertiary],
        },
      },
      splitLine: {
        lineStyle: {
          color: borderDefault,
        },
      },
      axisLine: {
        lineStyle: {
          color: borderDefault,
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
        areaStyle: { opacity: 0.3, color: accent },
        lineStyle: { color: accent, width: 2 },
        itemStyle: { color: accent },
      }],
    }],
    tooltip: {
      trigger: 'item',
      backgroundColor: bgElevated,
      borderColor: borderDefault,
      textStyle: { color: textPrimary },
    },
  };

  return <ReactECharts echarts={echarts} option={option} style={{ height: isMobile ? 240 : 300 }} role="img" aria-label="评分雷达图" />;
}