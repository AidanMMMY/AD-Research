import React from 'react';
import { Tag } from 'antd';

export type ThemeTagVariant =
  | 'default'
  | 'accent'
  | 'rise'
  | 'fall'
  | 'success'
  | 'error'
  | 'warning'
  | 'neutral';

interface ThemeTagProps {
  variant?: ThemeTagVariant;
  children: React.ReactNode;
  style?: React.CSSProperties;
  className?: string;
  onClick?: React.MouseEventHandler<HTMLSpanElement>;
}

const variantStyles: Record<ThemeTagVariant, React.CSSProperties> = {
  default: {
    background: 'transparent',
    borderColor: 'var(--border-default)',
    color: 'var(--text-secondary)',
  },
  accent: {
    background: 'var(--accent-dim)',
    borderColor: 'var(--accent-border)',
    color: 'var(--accent)',
  },
  rise: {
    background: 'var(--color-rise-dim)',
    borderColor: 'var(--color-rise-border)',
    color: 'var(--color-rise)',
  },
  fall: {
    background: 'var(--color-fall-dim)',
    borderColor: 'var(--color-fall-border)',
    color: 'var(--color-fall)',
  },
  success: {
    background: 'var(--color-success-dim)',
    borderColor: 'var(--color-success-border)',
    color: 'var(--color-success)',
  },
  error: {
    background: 'var(--color-error-dim)',
    borderColor: 'var(--color-error-border)',
    color: 'var(--color-error)',
  },
  warning: {
    background: 'var(--color-warning-dim)',
    borderColor: 'var(--color-warning-border)',
    color: 'var(--color-warning)',
  },
  neutral: {
    background: 'var(--bg-hover)',
    borderColor: 'var(--border-default)',
    color: 'var(--text-tertiary)',
  },
};

/**
 * 主题化 Tag — 不使用 Ant Design 预设色，全部基于 design token。
 */
export default function ThemeTag({
  variant = 'default',
  children,
  style,
  className,
  onClick,
}: ThemeTagProps) {
  return (
    <Tag
      className={className}
      onClick={onClick}
      style={{
        borderRadius: 'var(--radius-sm)',
        fontSize: 'var(--text-small-size)',
        fontWeight: 500,
        padding: '2px 8px',
        lineHeight: 1.4,
        ...variantStyles[variant],
        ...style,
      }}
    >
      {children}
    </Tag>
  );
}
