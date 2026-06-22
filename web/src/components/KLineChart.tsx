import { useEffect, useRef, useState } from 'react';
import { createChart, IChartApi, ISeriesApi, CandlestickData, HistogramData, LineData, Time, ColorType, LineStyle } from 'lightweight-charts';
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
  const [initError, setInitError] = useState<string | null>(null);
  const [dataError, setDataError] = useState<string | null>(null);

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) return;

    try {
      const chart = createChart(chartContainerRef.current, {
        layout: {
          background: { type: ColorType.Solid, color: '#0f1729' },
          textColor: '#94a3b8',
        },
        grid: {
          vertLines: { color: 'rgba(255,255,255,0.06)' },
          horzLines: { color: 'rgba(255,255,255,0.06)' },
        },
        crosshair: { mode: 1 as any },
        rightPriceScale: { borderColor: 'rgba(255,255,255,0.08)' },
        timeScale: { borderColor: 'rgba(255,255,255,0.08)' },
        height: containerHeight,
      });

      chartRef.current = chart;

      const candlestick = chart.addCandlestickSeries({
        upColor: '#ef4444',
        downColor: '#22c55e',
        borderUpColor: '#ef4444',
        borderDownColor: '#22c55e',
        wickUpColor: '#ef4444',
        wickDownColor: '#22c55e',
      });
      candlestickRef.current = candlestick;

      const volume = chart.addHistogramSeries({
        color: '#06b6d4',
        priceFormat: { type: 'volume' },
        priceScaleId: '',
      });
      volume.priceScale().applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
      volumeRef.current = volume;

      const maOptions = { lastValueVisible: false, priceLineVisible: false, priceScaleId: 'right' };
      ma5Ref.current = chart.addLineSeries({ color: '#eab308', lineWidth: 1, ...maOptions });
      ma10Ref.current = chart.addLineSeries({ color: '#22c55e', lineWidth: 1, ...maOptions });
      ma20Ref.current = chart.addLineSeries({ color: '#ef4444', lineWidth: 1, ...maOptions });
      ma60Ref.current = chart.addLineSeries({ color: '#6366f1', lineWidth: 1, ...maOptions });

      bbUpperRef.current = chart.addLineSeries({ color: '#06b6d4', lineWidth: 1, lineStyle: LineStyle.Dashed, ...maOptions });
      bbLowerRef.current = chart.addLineSeries({ color: '#06b6d4', lineWidth: 1, lineStyle: LineStyle.Dashed, ...maOptions });

      rsiRef.current = chart.addLineSeries({
        color: '#6366f1',
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
      macdDifRef.current = chart.addLineSeries({ color: '#eab308', lineWidth: 1, priceScaleId: 'macd', lastValueVisible: false, priceLineVisible: false });
      macdDeaRef.current = chart.addLineSeries({ color: '#6366f1', lineWidth: 1, priceScaleId: 'macd', lastValueVisible: false, priceLineVisible: false });

      const handleResize = () => {
        if (chartContainerRef.current) {
          chart.applyOptions({ width: chartContainerRef.current.clientWidth });
        }
      };
      window.addEventListener('resize', handleResize);

      const handleDoubleClick = () => {
        chart.timeScale().fitContent();
      };
      chartContainerRef.current?.addEventListener('dblclick', handleDoubleClick);

      return () => {
        window.removeEventListener('resize', handleResize);
        chartContainerRef.current?.removeEventListener('dblclick', handleDoubleClick);
        chart.remove();
      };
    } catch (e: any) {
      setInitError(e?.message || String(e));
    }
  }, [containerHeight]);

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
        color: d.close >= d.open ? '#ef4444' : '#22c55e',
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
          color: v >= 0 ? '#ef4444' : '#22c55e',
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
  }, [data, overlays]);

  if (initError) {
    return (
      <div style={{ padding: 20, color: '#ef4444', background: 'rgba(239,68,68,0.1)', borderRadius: 8 }}>
        <strong>图表初始化错误:</strong> {initError}
      </div>
    );
  }

  if (dataError) {
    return (
      <div style={{ padding: 20, color: '#ef4444', background: 'rgba(239,68,68,0.1)', borderRadius: 8 }}>
        <strong>数据渲染错误:</strong> {dataError}
      </div>
    );
  }

  return <div ref={chartContainerRef} style={{ width: '100%', height: containerHeight }} />;
}
