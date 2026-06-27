import React from 'react';
import Panel, { PanelVariant } from './Panel';

interface GlassCardProps {
  children: React.ReactNode;
  title?: React.ReactNode;
  extra?: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  hover?: boolean;
  padding?: 'sm' | 'md' | 'lg';
  glow?: boolean;
  variant?: PanelVariant;
}

/**
 * 兼容性包装：GlassCard 现在内部使用 Panel。
 * hover/glow 参数保留但不再产生视觉差异。
 * 默认 variant 为 default（Bento card surface with rounded corners & shadow）。
 */
export default function GlassCard({
  children,
  title,
  extra,
  className = '',
  style,
  padding = 'md',
  variant = 'default',
}: GlassCardProps) {
  return (
    <Panel
      title={title}
      extra={extra}
      className={`glass-card ${className}`}
      style={style}
      variant={variant}
      padding={padding}
      data-glass-padding={padding}
    >
      {children}
    </Panel>
  );
}
