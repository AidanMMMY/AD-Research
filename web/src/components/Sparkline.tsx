import { useMemo } from 'react';

export interface SparklineProps {
  /** 数据序列（已排序，最旧在前，最新在后） */
  data: number[];
  /** 主色；如不传则按首末值自动判断涨绿/跌红 */
  color?: string;
  width?: number;
  height?: number;
  /** 涨色（默认绿） */
  upColor?: string;
  /** 跌色（默认红） */
  downColor?: string;
  /** 是否用色彩约定（A 股=红涨绿跌） */
  chinaConvention?: boolean;
  strokeWidth?: number;
  className?: string;
  style?: React.CSSProperties;
}

const DEFAULT_UP = 'var(--color-success-bright)';
const DEFAULT_DOWN = 'var(--color-error-bright)';
const DEFAULT_UP_CN = 'var(--color-error-bright)';
const DEFAULT_DOWN_CN = 'var(--color-success-bright)';

/**
 * 80x20 迷你折线图。
 * - 数据归一化到 [0, height]
 * - 涨绿跌红根据首末值判断（A 股惯例下颜色翻转）
 */
export default function Sparkline({
  data,
  color,
  width = 80,
  height = 20,
  upColor = DEFAULT_UP,
  downColor = DEFAULT_DOWN,
  chinaConvention = false,
  strokeWidth = 1.25,
  className,
  style,
}: SparklineProps) {
  const path = useMemo(() => {
    if (!data || data.length === 0) return '';
    if (data.length === 1) {
      const y = height / 2;
      return `M0 ${y} L ${width} ${y}`;
    }
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const stepX = width / (data.length - 1);
    return data
      .map((v, i) => {
        const x = i * stepX;
        const y = height - ((v - min) / range) * height;
        return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(' ');
  }, [data, width, height]);

  const stroke = useMemo(() => {
    if (color) return color;
    if (!data || data.length < 2) return chinaConvention ? DEFAULT_UP_CN : DEFAULT_UP;
    const first = data[0];
    const last = data[data.length - 1];
    if (last === first) return chinaConvention ? DEFAULT_UP_CN : DEFAULT_UP;
    const up = last > first;
    if (chinaConvention) return up ? DEFAULT_UP_CN : DEFAULT_DOWN_CN;
    return up ? upColor : downColor;
  }, [color, data, chinaConvention, upColor, downColor]);

  if (!data || data.length === 0) {
    return (
      <span
        style={{
          display: 'inline-block',
          width,
          height,
          color: 'var(--text-tertiary)',
          fontSize: 11,
          lineHeight: `${height}px`,
          textAlign: 'center',
          ...style,
        }}
        className={className}
      >
        —
      </span>
    );
  }

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      style={{ display: 'inline-block', verticalAlign: 'middle', ...style }}
      className={className}
      aria-label="sparkline"
    >
      <path d={path} fill="none" stroke={stroke} strokeWidth={strokeWidth} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}