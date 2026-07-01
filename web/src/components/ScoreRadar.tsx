import { useEffect, useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { resolveChartColors } from '@/utils/cssVar';

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
  const [, setThemeTick] = useState(0);
  useEffect(() => {
    const handler = () => setThemeTick((t) => t + 1);
    document.addEventListener('themechange', handler);
    return () => document.removeEventListener('themechange', handler);
  }, []);

  const accent = useMemo(
    () => resolveChartColors(['var(--accent)'], ['#5fa87a'])[0],
    [],
  );
  const accentDim = useMemo(
    () => resolveChartColors(['var(--accent-dim)'], ['rgba(95,168,122,0.10)'])[0],
    [],
  );
  const textTertiary = useMemo(
    () => resolveChartColors(['var(--text-tertiary)'], ['#444444'])[0],
    [],
  );
  const textSecondary = useMemo(
    () => resolveChartColors(['var(--text-secondary)'], ['#888888'])[0],
    [],
  );
  const borderDefault = useMemo(
    () => resolveChartColors(['var(--border-default)'], ['rgba(255,255,255,0.06)'])[0],
    [],
  );
  const bgElevated = useMemo(
    () => resolveChartColors(['var(--bg-elevated)'], ['#111111'])[0],
    [],
  );
  const textPrimary = useMemo(
    () => resolveChartColors(['var(--text-primary)'], ['#f5f5f0'])[0],
    [],
  );

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

  return <ReactECharts option={option} style={{ height: isMobile ? 240 : 300 }} />;
}