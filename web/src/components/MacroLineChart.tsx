import { useEffect, useRef, useState } from 'react';
import {
  createChart,
  IChartApi,
  ISeriesApi,
  AreaData,
  Time,
  ColorType,
} from 'lightweight-charts';
import { readCssVar } from '@/utils/cssVar';
import { chartA11yProps } from '@/utils/a11y';

interface MacroLineChartProps {
  /** 折线数据点（period 为 YYYY-MM-DD）。 */
  points: Array<{ period: string; value: number }>;
  /** 数值单位（仅用于 aria-label 描述）。 */
  unit?: string;
  /** 图表高度，默认 420。 */
  height?: number;
}

/**
 * MacroLineChart — 宏观序列折线/面积图（lightweight-charts v4 AreaSeries）。
 *
 * 用于全球速览指数详情页中无 OHLC 的序列（FRED 利率/汇率等只有收盘值）。
 * 模式与 KLineChart 一致：主题色走 readCssVar（lightweight-charts 不认
 * CSS 变量）、ResizeObserver 容器自适应、数据变化时 setData + fitContent。
 */
export default function MacroLineChart({ points, unit, height = 420 }: MacroLineChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const areaRef = useRef<ISeriesApi<'Area'> | null>(null);
  const [initError, setInitError] = useState<string | null>(null);
  const [dataError, setDataError] = useState<string | null>(null);

  // 初始化图表（高度变化时重建）
  useEffect(() => {
    if (!chartContainerRef.current) return;

    try {
      const c = {
        bgBase: readCssVar('--bg-base', '#FAFBFC'),
        textSecondary: readCssVar('--text-secondary', '#5B6778'),
        borderDefault: readCssVar('--border-default', '#e5e7eb'),
        accent: readCssVar('--accent', '#2563EB'),
        accentDim: readCssVar('--accent-dim', 'rgba(37, 99, 235, 0.08)'),
      };

      const chart = createChart(chartContainerRef.current, {
        layout: {
          background: { type: ColorType.Solid, color: c.bgBase },
          textColor: c.textSecondary,
        },
        grid: {
          vertLines: { color: c.borderDefault },
          horzLines: { color: c.borderDefault },
        },
        crosshair: { mode: 1 as any },
        rightPriceScale: { borderColor: c.borderDefault },
        timeScale: { borderColor: c.borderDefault },
        height,
      });

      chartRef.current = chart;

      // 折线 + 淡填充（宏观序列惯用形态）
      const area = chart.addAreaSeries({
        lineColor: c.accent,
        topColor: c.accentDim,
        bottomColor: 'transparent',
        lineWidth: 2,
      });
      areaRef.current = area;

      const handleResize = () => {
        if (chartContainerRef.current) {
          chart.applyOptions({
            width: chartContainerRef.current.clientWidth,
            height: chartContainerRef.current.clientHeight || height,
          });
        }
      };

      // ResizeObserver 容器驱动自适应（窗口缩放 / 布局变化均生效）
      const ro = new ResizeObserver(handleResize);
      ro.observe(chartContainerRef.current);

      const handleDoubleClick = () => {
        chart.timeScale().fitContent();
      };
      chartContainerRef.current?.addEventListener('dblclick', handleDoubleClick);

      return () => {
        ro.disconnect();
        chartContainerRef.current?.removeEventListener('dblclick', handleDoubleClick);
        chart.remove();
      };
    } catch (e: any) {
      setInitError(e?.message || String(e));
    }
  }, [height]);

  // 数据更新：排序去重（lightweight-charts 要求时间严格升序且唯一）
  useEffect(() => {
    if (!areaRef.current) return;

    try {
      const seen = new Set<string>();
      const areaData: AreaData[] = points
        .filter((p) => p.period != null && p.value != null)
        .slice()
        .sort((a, b) => (a.period < b.period ? -1 : a.period > b.period ? 1 : 0))
        .filter((p) => {
          if (seen.has(p.period)) return false;
          seen.add(p.period);
          return true;
        })
        .map((p) => ({ time: p.period as Time, value: p.value }));

      areaRef.current.setData(areaData);
      chartRef.current?.timeScale().fitContent();
    } catch (e: any) {
      setDataError(e?.message || String(e));
    }
  }, [points]);

  if (initError) {
    return (
      <div className="kline-chart__error">
        <strong>图表初始化错误:</strong> {initError}
      </div>
    );
  }

  if (dataError) {
    return (
      <div className="kline-chart__error">
        <strong>数据渲染错误:</strong> {dataError}
      </div>
    );
  }

  return (
    <div
      ref={chartContainerRef}
      className="macro-line-chart"
      style={{ height }}
      {...chartA11yProps(`历史走势折线图${unit ? `（单位：${unit}）` : ''}`)}
    />
  );
}
