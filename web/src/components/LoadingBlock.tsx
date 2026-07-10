import { Spin } from 'antd';
import type { CSSProperties } from 'react';
import './LoadingBlock.css';

export type LoadingBlockSize = 'sm' | 'md' | 'lg';

const sizeMap: Record<LoadingBlockSize, 'small' | 'default' | 'large'> = {
  sm: 'small',
  md: 'default',
  lg: 'large',
};

export interface LoadingBlockProps {
  size?: LoadingBlockSize;
  label?: string;
  style?: CSSProperties;
}

export default function LoadingBlock({
  size = 'md',
  label,
  style,
}: LoadingBlockProps) {
  return (
    <div className="loading-block" style={style}>
      <Spin size={sizeMap[size]} />
      {label && <span className="ad-text-small ad-text-tertiary">{label}</span>}
    </div>
  );
}
