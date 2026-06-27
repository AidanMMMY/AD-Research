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
    borderColor: 'rgba(239, 68, 68, 0.25)',
    color: 'var(--color-rise)',
  },
  fall: {
    background: 'var(--color-fall-dim)',
    borderColor: 'rgba(34, 197, 94, 0.25)',
    color: 'var(--color-fall)',
  },
  success: {
    background: 'rgba(34, 197, 94, 0.08)',
    borderColor: 'rgba(34, 197, 94, 0.25)',
    color: '#22c55e',
  },
  error: {
    background: 'rgba(239, 68, 68, 0.08)',
    borderColor: 'rgba(239, 68, 68, 0.25)',
    color: '#ef4444',
  },
  warning: {
    background: 'rgba(234, 179, 8, 0.08)',
    borderColor: 'rgba(234, 179, 8, 0.25)',
    color: '#eab308',
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
