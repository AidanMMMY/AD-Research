import { useEffect, useRef, useState } from 'react';
import { createChart, IChartApi, ISeriesApi, CandlestickData, HistogramData, LineData, Time } from 'lightweight-charts';
import type { OHLCV } from '@/types/etf';

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

// Simple SMA calculator
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

// Bollinger Bands
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

// RSI
function calcRSI(data: { close: number }[], period: number = 14): (number | null)[] {
  const result: (number | null)[] = [];
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

// MACD
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

  const [containerHeight] = useState(500);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { color: '#ffffff' },
        textColor: '#333',
      },
      grid: {
        vertLines: { color: '#f0f0f0' },
        horzLines: { color: '#f0f0f0' },
      },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: '#d9d9d9' },
      timeScale: { borderColor: '#d9d9d9' },
      height: containerHeight,
    });

    chartRef.current = chart;

    // Main candlestick series
    const candlestick = chart.addCandlestickSeries({
      upColor: '#cf1322',
      downColor: '#3f8600',
      borderUpColor: '#cf1322',
      borderDownColor: '#3f8600',
      wickUpColor: '#cf1322',
      wickDownColor: '#3f8600',
    });
    candlestickRef.current = candlestick;

    // Volume on main pane (overlay)
    const volume = chart.addHistogramSeries({
      color: '#1890ff',
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
    volumeRef.current = volume;

    // MA lines on main pane
    const maOptions = { lastValueVisible: false, priceLineVisible: false, priceScaleId: 'right' };
    ma5Ref.current = chart.addLineSeries({ color: '#ff7f0e', lineWidth: 1, ...maOptions });
    ma10Ref.current = chart.addLineSeries({ color: '#2ca02c', lineWidth: 1, ...maOptions });
    ma20Ref.current = chart.addLineSeries({ color: '#d62728', lineWidth: 1, ...maOptions });
    ma60Ref.current = chart.addLineSeries({ color: '#9467bd', lineWidth: 1, ...maOptions });

    // Bollinger Bands
    bbUpperRef.current = chart.addLineSeries({ color: '#17becf', lineWidth: 1, lineStyle: 2, ...maOptions });
    bbLowerRef.current = chart.addLineSeries({ color: '#17becf', lineWidth: 1, lineStyle: 2, ...maOptions });

    // RSI pane
    rsiRef.current = chart.addLineSeries({
      color: '#e377c2',
      lineWidth: 1,
      lastValueVisible: false,
      priceLineVisible: false,
      priceScaleId: 'rsi',
    });
    chart.priceScale('rsi').applyOptions({
      scaleMargins: { top: 0.1, bottom: 0.1 },
      visible: false,
    });

    // MACD pane
    macdHistRef.current = chart.addHistogramSeries({
      priceScaleId: 'macd',
      lastValueVisible: false,
      priceLineVisible: false,
    });
    macdDifRef.current = chart.addLineSeries({ color: '#ff7f0e', lineWidth: 1, priceScaleId: 'macd', lastValueVisible: false, priceLineVisible: false });
    macdDeaRef.current = chart.addLineSeries({ color: '#1f77b4', lineWidth: 1, priceScaleId: 'macd', lastValueVisible: false, priceLineVisible: false });
    chart.priceScale('macd').applyOptions({
      scaleMargins: { top: 0.2, bottom: 0.2 },
      visible: false,
    });

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [containerHeight]);

  // Update data when props change
  useEffect(() => {
    if (!data.length || !candlestickRef.current || !volumeRef.current) return;

    const times = data.map((d) => d.trade_date.replace(/-/g, '/') as Time);

    const candleData: CandlestickData[] = data.map((d) => ({
      time: d.trade_date.replace(/-/g, '/') as Time,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));

    const volumeData: HistogramData[] = data.map((d) => ({
      time: d.trade_date.replace(/-/g, '/') as Time,
      value: d.volume,
      color: d.close >= d.open ? '#cf1322' : '#3f8600',
    }));

    candlestickRef.current.setData(candleData);
    volumeRef.current.setData(volumeData);

    // MA overlays
    const ma5Data = calcSMA(data, 5);
    const ma10Data = calcSMA(data, 10);
    const ma20Data = calcSMA(data, 20);
    const ma60Data = calcSMA(data, 60);

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

    // Bollinger Bands
    if (overlays.bb) {
      const bb = calcBB(data, 20, 2);
      bbUpperRef.current?.setData(toLineData(bb.upper));
      bbLowerRef.current?.setData(toLineData(bb.lower));
    } else {
      bbUpperRef.current?.setData([]);
      bbLowerRef.current?.setData([]);
    }

    // RSI
    if (overlays.rsi) {
      const rsiData = calcRSI(data, 14);
      rsiRef.current?.setData(toLineData(rsiData));
      chartRef.current?.priceScale('rsi').applyOptions({ visible: true });
    } else {
      rsiRef.current?.setData([]);
      chartRef.current?.priceScale('rsi').applyOptions({ visible: false });
    }

    // MACD
    if (overlays.macd) {
      const macd = calcMACD(data, 12, 26, 9);
      const histData: HistogramData[] = macd.hist.map((v, i) => ({
        time: times[i],
        value: v,
        color: v >= 0 ? '#cf1322' : '#3f8600',
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
  }, [data, overlays]);

  return <div ref={chartContainerRef} style={{ width: '100%', height: containerHeight }} />;
}
