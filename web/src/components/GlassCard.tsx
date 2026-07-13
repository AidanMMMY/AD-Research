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
 * GlassCard — translucent surface wrapper used throughout the dashboard.
 *
 *  - ``hover`` adds a subtle border + lift on pointer hover so the card
 *    reads as interactive even when no click handler is wired yet.
 *  - ``glow`` adds a soft accent halo behind the card (used sparingly
 *    for hero / CTA surfaces).
 *
 *  Both props apply CSS classes; the actual styles live in the shared
 *  stylesheet alongside the rest of the design system tokens.
 */
export default function GlassCard({
  children,
  title,
  extra,
  className = '',
  style,
  hover = false,
  padding = 'md',
  glow = false,
  variant = 'minimal',
}: GlassCardProps) {
  const cls = [
    'glass-card',
    hover ? 'glass-card--hover' : '',
    glow ? 'glass-card--glow' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <Panel
      title={title}
      extra={extra}
      className={cls}
      style={style}
      variant={variant}
      padding={padding}
    >
      {children}
    </Panel>
  );
}
