import type { CSSProperties } from 'react';
import './LoadingBlock.css';

export type LoadingBlockSize = 'sm' | 'md' | 'lg';

interface SkeletonConfig {
  short: number[];
  medium: number[];
  long: number[];
}

const skeletonConfig: Record<LoadingBlockSize, SkeletonConfig> = {
  sm: {
    short: [40, 55, 35],
    medium: [],
    long: [85],
  },
  md: {
    short: [],
    medium: [60, 75, 50, 65],
    long: [90, 95],
  },
  lg: {
    short: [],
    medium: [60, 80, 45, 70, 55, 65],
    long: [95, 90, 85],
  },
};

export interface LoadingBlockProps {
  size?: LoadingBlockSize;
  label?: string;
  className?: string;
  style?: CSSProperties;
}

export default function LoadingBlock({
  size = 'md',
  label,
  className,
  style,
}: LoadingBlockProps) {
  const config = skeletonConfig[size];

  return (
    <div
      className={`loading-block ${className ?? ''}`.trim()}
      aria-busy="true"
      aria-label="正在加载内容"
      style={style}
    >
      <div className="loading-block__bars">
        {config.short.map((widthPct, i) => (
          <div
            key={`s-${i}`}
            className="loading-block__bar loading-block__bar--short skeleton-shimmer"
            style={{ width: `${widthPct}%` }}
          />
        ))}
        {config.medium.map((widthPct, i) => (
          <div
            key={`m-${i}`}
            className="loading-block__bar loading-block__bar--medium skeleton-shimmer"
            style={{ width: `${widthPct}%` }}
          />
        ))}
        {config.long.map((widthPct, i) => (
          <div
            key={`l-${i}`}
            className="loading-block__bar loading-block__bar--long skeleton-shimmer"
            style={{ width: `${widthPct}%` }}
          />
        ))}
      </div>
      {label && <span className="loading-block__label">{label}</span>}
    </div>
  );
}
