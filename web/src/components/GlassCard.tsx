import React from 'react';

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
 * 玻璃拟态卡片，padding 在移动端自适应缩小。
 * sm: 紧凑, md: 默认, lg: 宽松
 */
const paddingMap: Record<string, { desktop: [number, number]; mobile: [number, number] }> = {
  sm: { desktop: [16, 20], mobile: [12, 14] },
  md: { desktop: [20, 24], mobile: [14, 16] },
  lg: { desktop: [24, 28], mobile: [16, 18] },
};

export default function GlassCard({
  children,
  title,
  extra,
  className = '',
  style,
  hover = true,
  padding = 'md',
  glow = false,
}: GlassCardProps) {
  const p = paddingMap[padding];

  return (
    <div
      className={`glass-card ${className}`}
      data-glass-padding={padding}
      style={{
        background: 'rgba(255, 255, 255, 0.03)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        border: '1px solid rgba(255, 255, 255, 0.06)',
        borderRadius: '16px',
        boxShadow: glow
          ? '0 4px 24px rgba(99, 102, 241, 0.15), inset 0 1px 0 rgba(255,255,255,0.05)'
          : '0 4px 24px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255,255,255,0.05)',
        transition: 'all 250ms cubic-bezier(0.4, 0, 0.2, 1)',
        ...(hover && {
          cursor: 'default',
        }),
        ...style,
      }}
      onMouseEnter={(e) => {
        if (hover) {
          const el = e.currentTarget;
          el.style.borderColor = 'rgba(255, 255, 255, 0.12)';
          el.style.boxShadow = glow
            ? '0 8px 40px rgba(99, 102, 241, 0.25), inset 0 1px 0 rgba(255,255,255,0.08)'
            : '0 8px 40px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255,255,255,0.08)';
          el.style.transform = 'translateY(-2px)';
        }
      }}
      onMouseLeave={(e) => {
        if (hover) {
          const el = e.currentTarget;
          el.style.borderColor = 'rgba(255, 255, 255, 0.06)';
          el.style.boxShadow = glow
            ? '0 4px 24px rgba(99, 102, 241, 0.15), inset 0 1px 0 rgba(255,255,255,0.05)'
            : '0 4px 24px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255,255,255,0.05)';
          el.style.transform = 'translateY(0)';
        }
      }}
    >
      {(title || extra) && (
        <div
          className="glass-card-header"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: `${p.desktop[0]}px ${p.desktop[1]}px 12px`,
            borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
            gap: 12,
            minWidth: 0,
          }}
        >
          {title && (
            <span
              style={{
                fontSize: '16px',
                fontWeight: 600,
                color: '#f1f5f9',
                letterSpacing: '0.3px',
                lineHeight: '24px',
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
        className="glass-card-body"
        style={{
          padding: title
            ? `12px ${p.desktop[1]}px ${p.desktop[0]}px`
            : `${p.desktop[0]}px ${p.desktop[1]}px`,
        }}
      >
        {children}
      </div>
    </div>
  );
}
