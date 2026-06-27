import React from 'react';
import Panel from './Panel';

interface GlassCardProps {
  children: React.ReactNode;
  title?: React.ReactNode;
  extra?: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  hover?: boolean;
  padding?: 'sm' | 'md' | 'lg';
  glow?: boolean;
}

/**
 * 兼容性包装：GlassCard 现在内部使用 Panel。
 * hover/glow 参数保留但不再产生视觉差异。
 */
export default function GlassCard({
  children,
  title,
  extra,
  className = '',
  style,
  padding = 'md',
}: GlassCardProps) {
  return (
    <Panel
      title={title}
      extra={extra}
      className={`glass-card ${className}`}
      style={style}
      padding={padding}
      data-glass-padding={padding}
    >
      {children}
    </Panel>
  );
}
