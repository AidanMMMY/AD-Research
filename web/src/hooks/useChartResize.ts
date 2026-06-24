import { useEffect, useRef, useCallback } from 'react';
import type { ECharts } from 'echarts';
import { useIsMobile } from './useBreakpoint';

/**
 * ECharts 容器自适应 hook。
 * 使用 ResizeObserver 监听父容器尺寸变化并自动 resize。
 * 同时提供 isMobile 标志供图表配置简化使用。
 */
export function useChartResize(chartInstance: ECharts | null) {
  const roRef = useRef<ResizeObserver | null>(null);

  useEffect(() => {
    if (!chartInstance) return;

    const dom = chartInstance.getDom();
    if (!dom) return;

    const parent = dom.parentElement || dom;
    const ro = new ResizeObserver(() => {
      chartInstance.resize();
    });
    ro.observe(parent);
    roRef.current = ro;

    return () => {
      ro.disconnect();
      roRef.current = null;
    };
  }, [chartInstance]);
}

/**
 * 获取 ECharts 实例的便捷 callback ref。
 * 搭配 ReactECharts 的 `ref` 属性使用。
 */
export function useEChartsRef() {
  const chartRef = useRef<ECharts | null>(null);
  const isMobile = useIsMobile();

  const setChartRef = useCallback((instance: any) => {
    // ReactECharts ref 回调参数是 ReactECharts 实例，其 getEchartsInstance() 返回 ECharts 实例
    chartRef.current = instance?.getEchartsInstance?.() ?? null;
  }, []);

  useChartResize(chartRef.current);

  return { chartRef, setChartRef, isMobile };
}
