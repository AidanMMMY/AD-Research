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
  'data-glass-padding'?: string;
}

const paddingMap = {
  none: { desktop: 0, mobile: 0 },
  sm: { desktop: 16, mobile: 12 },
  md: { desktop: 24, mobile: 16 },
  lg: { desktop: 32, mobile: 20 },
};

export default function Panel({
  children,
  title,
  extra,
  className = '',
  style,
  variant = 'default',
  padding = 'md',
  'data-glass-padding': dataGlassPadding,
}: PanelProps) {
  const p = paddingMap[padding];

  const isDefault = variant === 'default';
  const isMinimal = variant === 'minimal';
  const showHeaderBorder = isDefault || isMinimal;

  return (
    <div
      className={`swiss-panel ${className}`}
      data-glass-padding={dataGlassPadding}
      style={{
        background: isDefault ? 'var(--bg-elevated)' : 'transparent',
        border: isDefault ? '1px solid var(--border-default)' : 'none',
        borderRadius: 0,
        ...style,
      }}
    >
      {(title || extra) && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: `${p.desktop}px ${p.desktop}px 12px`,
            borderBottom: showHeaderBorder ? '1px solid var(--border-default)' : 'none',
            gap: 12,
            minWidth: 0,
          }}
        >
          {title && (
            <span
              style={{
                fontSize: 'var(--text-label-size)',
                fontWeight: 500,
                color: 'var(--text-tertiary)',
                letterSpacing: '0.08em',
                lineHeight: 1.4,
                textTransform: 'uppercase',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                flex: '1 1 auto',
                minWidth: 0,
              }}
            >
              {title}
            </span>
          )}
          {extra && <div style={{ flexShrink: 0 }}>{extra}</div>}
        </div>
      )}
      <div
        style={{
          padding: title
            ? `12px ${p.desktop}px ${p.desktop}px`
            : `${p.desktop}px`,
        }}
      >
        {children}
      </div>
    </div>
  );
}
