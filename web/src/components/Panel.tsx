import React from 'react';

export type PanelVariant = 'default' | 'minimal' | 'transparent';

export interface PanelProps {
  children: React.ReactNode;
  title?: React.ReactNode;
  extra?: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  variant?: PanelVariant;
  padding?: 'none' | 'sm' | 'md' | 'lg';
}

export default function Panel({
  children,
  title,
  extra,
  className = '',
  style,
  variant = 'default',
  padding = 'md',
}: PanelProps) {
  const variantClass = variant === 'default' ? 'ad-panel--default' : `ad-panel--${variant}`;

  return (
    <div
      className={`ad-panel ${variantClass} ad-panel--padding-${padding} ${className}`}
      style={style}
    >
      {(title || extra) && (
        <div className="ad-panel__header">
          {title && <span className="ad-panel__title">{title}</span>}
          {extra && <div className="ad-panel__extra">{extra}</div>}
        </div>
      )}
      <div className="ad-panel__body">{children}</div>
    </div>
  );
}
