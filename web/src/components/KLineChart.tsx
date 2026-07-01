import { useEffect, useMemo, useRef, useState } from 'react';
import { createChart, IChartApi, ISeriesApi, CandlestickData, HistogramData, LineData, Time, ColorType, LineStyle } from 'lightweight-charts';
import type { OHLCV } from '@/types/instrument';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { useSettingsStore } from '@/stores/settings';
import { getUpColor, getDownColor } from '@/utils/color';

interface IndicatorOverlay {
  ma5?: boolean;
  ma10?: boolean;
  ma20?: boolean;
  ma60?: boolean;
  bb?: boolean;
  rsi?: boolean;
  macd?: boolean;
}

interface KLineChartProps {
  data: OHLCV[];
  overlays?: IndicatorOverlay;
}

function calcSMA(data: { close: number }[], period: number): (number | null)[] {
  const result: (number | null)[] = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      result.push(null);
    } else {
      let sum = 0;
      for (let j = 0; j < period; j++) {
        sum += data[i - j].close;
      }
      result.push(sum / period);
    }
  }
  return result;
}

function calcBB(data: { close: number }[], period: number = 20, stdDev: number = 2) {
  const upper: (number | null)[] = [];
  const lower: (number | null)[] = [];
  const sma = calcSMA(data, period);
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1 || sma[i] === null) {
      upper.push(null);
      lower.push(null);
    } else {
      let sumSq = 0;
      for (let j = 0; j < period; j++) {
        const diff = data[i - j].close - (sma[i] as number);
        sumSq += diff * diff;
      }
      const std = Math.sqrt(sumSq / period);
      upper.push((sma[i] as number) + stdDev * std);
      lower.push((sma[i] as number) - stdDev * std);
    }
  }
  return { upper, lower, sma };
}

function calcRSI(data: { close: number }[], period: number = 14): (number | null)[] {
  const result: (number | null)[] = [];
  if (data.length <= period) {
    return data.map(() => null);
  }
  let gains = 0;
  let losses = 0;
  for (let i = 1; i <= period; i++) {
    const change = data[i].close - data[i - 1].close;
    if (change > 0) gains += change;
    else losses -= change;
  }
  let avgGain = gains / period;
  let avgLoss = losses / period;
  for (let i = 0; i < data.length; i++) {
    if (i < period) {
      result.push(null);
    } else {
      if (i > period) {
        const change = data[i].close - data[i - 1].close;
        const gain = change > 0 ? change : 0;
        const loss = change < 0 ? -change : 0;
        avgGain = (avgGain * (period - 1) + gain) / period;
        avgLoss = (avgLoss * (period - 1) + loss) / period;
      }
      if (avgLoss === 0) {
        result.push(100);
      } else {
        const rs = avgGain / avgLoss;
        result.push(100 - 100 / (1 + rs));
      }
    }
  }
  return result;
}

function calcMACD(data: { close: number }[], fast: number = 12, slow: number = 26, signal: number = 9) {
  const ema = (arr: number[], period: number): number[] => {
    const k = 2 / (period + 1);
    const result: number[] = [arr[0]];
    for (let i = 1; i < arr.length; i++) {
      result.push(arr[i] * k + result[i - 1] * (1 - k));
    }
    return result;
  };
  const closes = data.map((d) => d.close);
  const emaFast = ema(closes, fast);
  const emaSlow = ema(closes, slow);
  const dif = emaFast.map((v, i) => v - emaSlow[i]);
  const dea = ema(dif, signal);
  const hist = dif.map((v, i) => v - dea[i]);
  return { dif, dea, hist };
}

export const DEFAULT_OVERLAYS: IndicatorOverlay = {
  ma5: true,
  ma10: false,
  ma20: true,
  ma60: false,
  bb: false,
  rsi: true,
  macd: false,
};

/**
 * Resolve a CSS custom property to an actual color value.
 * lightweight-charts cannot parse CSS variables like `var(--text-secondary)`,
 * so we read the computed value from :root before passing it to the chart.
 */
function getCssColor(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/** Resolve a color string, converting CSS variables to concrete values. */
function resolveChartColor(color: string, fallback: string): string {
  if (color.startsWith('var(')) {
    const varName = color.slice(4, -1).trim();
    return getCssColor(varName, fallback);
  }
  return color;
}

export default function KLineChart({ data, overlays = DEFAULT_OVERLAYS }: KLineChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlestickRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const ma5Ref = useRef<ISeriesApi<'Line'> | null>(null);
  const ma10Ref = useRef<ISeriesApi<'Line'> | null>(null);
  const ma20Ref = useRef<ISeriesApi<'Line'> | null>(null);
  const ma60Ref = useRef<ISeriesApi<'Line'> | null>(null);
  const bbUpperRef = useRef<ISeriesApi<'Line'> | null>(null);
  const bbLowerRef = useRef<ISeriesApi<'Line'> | null>(null);
  const rsiRef = useRef<ISeriesApi<'Line'> | null>(null);
  const macdHistRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const macdDifRef = useRef<ISeriesApi<'Line'> | null>(null);
  const macdDeaRef = useRef<ISeriesApi<'Line'> | null>(null);

  const isMobile = useIsMobile();
  const colorConvention = useSettingsStore((s) => s.colorConvention);
  const upColor = getUpColor(colorConvention);
  const downColor = getDownColor(colorConvention);
  const resolvedUpColor = useMemo(
    () => resolveChartColor(upColor, '#c96b6b'),
    [upColor]
  );
  const resolvedDownColor = useMemo(
    () => resolveChartColor(downColor, '#5fa87a'),
    [downColor]
  );
  const containerHeight = isMobile ? 350 : 500;
  const [initError, setInitError] = useState<string | null>(null);
  const [dataError, setDataError] = useState<string | null>(null);

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) return;

    try {
      const c = {
        bgBase: getCssColor('--bg-base', '#0a0a0a'),
        textSecondary: getCssColor('--text-secondary', '#888888'),
        textTertiary: getCssColor('--text-tertiary', '#444444'),
        borderDefault: getCssColor('--border-default', 'rgba(255, 255, 255, 0.06)'),
        accent: getCssColor('--accent', '#5fa87a'),
        accentDim: getCssColor('--accent-dim', 'rgba(95, 168, 122, 0.10)'),
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
        height: containerHeight,
      });

      chartRef.current = chart;

      const candlestick = chart.addCandlestickSeries({
        upColor: resolvedUpColor,
        downColor: resolvedDownColor,
        borderUpColor: resolvedUpColor,
        borderDownColor: resolvedDownColor,
        wickUpColor: resolvedUpColor,
        wickDownColor: resolvedDownColor,
      });
      candlestickRef.current = candlestick;

      const volume = chart.addHistogramSeries({
        color: c.accentDim,
        priceFormat: { type: 'volume' },
        priceScaleId: '',
      });
      volume.priceScale().applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
      volumeRef.current = volume;

      const maOptions = { lastValueVisible: false, priceLineVisible: false, priceScaleId: 'right' };
      ma5Ref.current = chart.addLineSeries({ color: c.accent, lineWidth: 1, ...maOptions });
      ma10Ref.current = chart.addLineSeries({ color: c.textSecondary, lineWidth: 1, ...maOptions });
      ma20Ref.current = chart.addLineSeries({ color: c.accentDim, lineWidth: 1, ...maOptions });
      ma60Ref.current = chart.addLineSeries({ color: c.textTertiary, lineWidth: 1, ...maOptions });

      bbUpperRef.current = chart.addLineSeries({ color: c.accent, lineWidth: 1, lineStyle: LineStyle.Dashed, ...maOptions });
      bbLowerRef.current = chart.addLineSeries({ color: c.accent, lineWidth: 1, lineStyle: LineStyle.Dashed, ...maOptions });

      rsiRef.current = chart.addLineSeries({
        color: c.textTertiary,
        lineWidth: 1,
        lastValueVisible: false,
        priceLineVisible: false,
        priceScaleId: 'rsi',
      });

      macdHistRef.current = chart.addHistogramSeries({
        priceScaleId: 'macd',
        lastValueVisible: false,
        priceLineVisible: false,
      });
      macdDifRef.current = chart.addLineSeries({ color: c.textTertiary, lineWidth: 1, priceScaleId: 'macd', lastValueVisible: false, priceLineVisible: false });
      macdDeaRef.current = chart.addLineSeries({ color: c.accent, lineWidth: 1, priceScaleId: 'macd', lastValueVisible: false, priceLineVisible: false });

      const handleResize = () => {
        if (chartContainerRef.current) {
          chart.applyOptions({ width: chartContainerRef.current.clientWidth, height: chartContainerRef.current.clientHeight || containerHeight });
        }
      };

      // Use ResizeObserver for container-driven resize (works for drawer open/close, orientation change etc.)
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
  }, [containerHeight, resolvedUpColor, resolvedDownColor]);

  // Update data
  useEffect(() => {
    if (!data.length || !candlestickRef.current || !volumeRef.current) return;

    try {
      const validData = data.filter(
        (d) => d.trade_date && d.open != null && d.high != null && d.low != null && d.close != null
      );
      if (!validData.length) return;

      const toTime = (d: { trade_date: string }) => d.trade_date as Time;
      const times = validData.map(toTime);

      const candleData: CandlestickData[] = validData.map((d) => ({
        time: toTime(d),
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
      }));

      const volumeData: HistogramData[] = validData.map((d) => ({
        time: toTime(d),
        value: d.volume ?? 0,
        color: d.close >= d.open ? resolvedUpColor : resolvedDownColor,
      }));

      candlestickRef.current.setData(candleData);
      volumeRef.current.setData(volumeData);

      const ma5Data = calcSMA(validData, 5);
      const ma10Data = calcSMA(validData, 10);
      const ma20Data = calcSMA(validData, 20);
      const ma60Data = calcSMA(validData, 60);

      const toLineData = (values: (number | null)[]): LineData[] =>
        values
          .map((v, i) => (v !== null ? { time: times[i], value: v } : null))
          .filter((d): d is LineData => d !== null);

      if (overlays.ma5) ma5Ref.current?.setData(toLineData(ma5Data));
      else ma5Ref.current?.setData([]);

      if (overlays.ma10) ma10Ref.current?.setData(toLineData(ma10Data));
      else ma10Ref.current?.setData([]);

      if (overlays.ma20) ma20Ref.current?.setData(toLineData(ma20Data));
      else ma20Ref.current?.setData([]);

      if (overlays.ma60) ma60Ref.current?.setData(toLineData(ma60Data));
      else ma60Ref.current?.setData([]);

      if (overlays.bb) {
        const bb = calcBB(validData, 20, 2);
        bbUpperRef.current?.setData(toLineData(bb.upper));
        bbLowerRef.current?.setData(toLineData(bb.lower));
      } else {
        bbUpperRef.current?.setData([]);
        bbLowerRef.current?.setData([]);
      }

      if (overlays.rsi) {
        const rsiData = calcRSI(validData, 14);
        rsiRef.current?.setData(toLineData(rsiData));
        chartRef.current?.priceScale('rsi').applyOptions({ visible: true });
      } else {
        rsiRef.current?.setData([]);
        chartRef.current?.priceScale('rsi').applyOptions({ visible: false });
      }

      if (overlays.macd) {
        const macd = calcMACD(validData, 12, 26, 9);
        const histData: HistogramData[] = macd.hist.map((v, i) => ({
          time: times[i],
          value: v,
          color: v >= 0 ? resolvedUpColor : resolvedDownColor,
        }));
        macdHistRef.current?.setData(histData);
        macdDifRef.current?.setData(toLineData(macd.dif));
        macdDeaRef.current?.setData(toLineData(macd.dea));
        chartRef.current?.priceScale('macd').applyOptions({ visible: true });
      } else {
        macdHistRef.current?.setData([]);
        macdDifRef.current?.setData([]);
        macdDeaRef.current?.setData([]);
        chartRef.current?.priceScale('macd').applyOptions({ visible: false });
      }

      chartRef.current?.timeScale().fitContent();
    } catch (e: any) {
      setDataError(e?.message || String(e));
    }
  }, [data, overlays, resolvedUpColor, resolvedDownColor]);

  // Update candlestick colors when convention changes
  useEffect(() => {
    if (candlestickRef.current) {
      candlestickRef.current.applyOptions({
        upColor: resolvedUpColor,
        downColor: resolvedDownColor,
        borderUpColor: resolvedUpColor,
        borderDownColor: resolvedDownColor,
        wickUpColor: resolvedUpColor,
        wickDownColor: resolvedDownColor,
      });
    }
  }, [resolvedUpColor, resolvedDownColor]);

  if (initError) {
    return (
      <div style={{ padding: 20, color: 'var(--color-rise)', background: 'var(--color-rise-dim)', borderRadius: 8 }}>
        <strong>图表初始化错误:</strong> {initError}
      </div>
    );
  }

  if (dataError) {
    return (
      <div style={{ padding: 20, color: 'var(--color-rise)', background: 'var(--color-rise-dim)', borderRadius: 8 }}>
        <strong>数据渲染错误:</strong> {dataError}
      </div>
    );
  }

  return <div ref={chartContainerRef} style={{ width: '100%', height: containerHeight }} />;
}
