import { useEffect, useMemo, useRef, useState } from 'react';

export interface SparklineProps {
  /** 数据序列（已排序，最旧在前，最新在后） */
  data: number[];
  /** 主色；如不传则按首末值自动判断涨跌并使用当前颜色约定 */
  color?: string;
  width?: number | string;
  height?: number;
  /** 涨色；默认使用当前颜色约定下的 --color-rise */
  upColor?: string;
  /** 跌色；默认使用当前颜色约定下的 --color-fall */
  downColor?: string;
  strokeWidth?: number;
  className?: string;
  style?: React.CSSProperties;
}

const DEFAULT_UP = 'var(--color-rise)';
const DEFAULT_DOWN = 'var(--color-fall)';

/**
 * 80x20 迷你折线图。
 * - 数据归一化到 [0, height]
 * - 颜色自动跟随当前颜色约定（红涨绿跌 / 绿涨红跌）
 */
export default function Sparkline({
  data,
  color,
  width = 80,
  height = 20,
  upColor = DEFAULT_UP,
  downColor = DEFAULT_DOWN,
  strokeWidth = 1.25,
  className,
  style,
}: SparklineProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [measuredWidth, setMeasuredWidth] = useState<number>(
    typeof width === 'number' ? width : 0,
  );

  useEffect(() => {
    if (typeof width === 'number') return;
    const svg = svgRef.current;
    if (!svg) return;
    const update = () => setMeasuredWidth(svg.getBoundingClientRect().width);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(svg);
    return () => ro.disconnect();
  }, [width]);

  const effectiveWidth = typeof width === 'number' ? width : measuredWidth;
  const path = useMemo(() => {
    if (!data || data.length === 0) return '';
    if (data.length === 1) {
      const y = height / 2;
      return `M0 ${y} L ${effectiveWidth} ${y}`;
    }
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const stepX = effectiveWidth / (data.length - 1);
    return data
      .map((v, i) => {
        const x = i * stepX;
        const y = height - ((v - min) / range) * height;
        return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(' ');
  }, [data, effectiveWidth, height]);

  const stroke = useMemo(() => {
    if (color) return color;
    if (!data || data.length < 2) return upColor;
    const first = data[0];
    const last = data[data.length - 1];
    if (last === first) return upColor;
    return last > first ? upColor : downColor;
  }, [color, data, upColor, downColor]);

  const areaPath = useMemo(() => {
    if (!path) return '';
    return `${path} L ${effectiveWidth} ${height} L 0 ${height} Z`;
  }, [path, effectiveWidth, height]);

  const gradientId = useMemo(
    () => `spark-grad-${Math.random().toString(36).slice(2, 9)}`,
    [stroke]
  );

  if (!data || data.length === 0) {
    return (
      <span
        className={`sparkline__empty ${className || ''}`}
        style={{
          // dynamic: empty placeholder dimensions come from props
          maxWidth: width,
          height,
          lineHeight: `${height}px`,
          ...style,
        }}
      >
        —
      </span>
    );
  }

  // Compute direction for the right-edge arrow marker (color-blind friendly cue).
  // We render a tiny triangle inside the SVG so it scales with the same width/height
  // and does not cause layout reflow in callers.
  const directionMarker = useMemo(() => {
    if (!data || data.length < 2) return null;
    const first = data[0];
    const last = data[data.length - 1];
    if (last === first) return null;
    const up = last > first;
    // triangle pointing up or down, sized within the height
    const cx = effectiveWidth - 3;
    const cy = height / 2;
    const half = Math.min(2.2, height / 4 - 0.5);
    if (up) {
      // apex up: (cx, cy-half), base at (cx-half, cy+half/2), (cx+half, cy+half/2)
      return `M ${cx} ${cy - half} L ${cx - half} ${cy + half / 2} L ${cx + half} ${cy + half / 2} Z`;
    }
    // apex down: (cx, cy+half)
    return `M ${cx} ${cy + half} L ${cx - half} ${cy - half / 2} L ${cx + half} ${cy - half / 2} Z`;
  }, [data, effectiveWidth, height]);

  // aria-label that includes direction so screen-reader users also get the cue.
  const ariaLabel = (() => {
    if (!data || data.length < 2) return 'sparkline';
    const first = data[0];
    const last = data[data.length - 1];
    if (last === first) return 'sparkline flat';
    return last > first ? 'sparkline up' : 'sparkline down';
  })();

  return (
    <svg
      ref={svgRef}
      width={width}
      height={height}
      viewBox={`0 0 ${Math.max(effectiveWidth, 1)} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      className={`sparkline ${className || ''}`}
      style={{
        maxWidth: '100%',
        height: 'auto',
        ...style,
      }}
      aria-label={ariaLabel}
      role={data && data.length >= 2 ? 'img' : undefined}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.28" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      {areaPath && <path d={areaPath} fill={`url(#${gradientId})`} stroke="none" />}
      <path d={path} fill="none" stroke={stroke} strokeWidth={strokeWidth} strokeLinejoin="round" strokeLinecap="round" />
      {directionMarker && <path d={directionMarker} fill={stroke} />}
    </svg>
  );
}
