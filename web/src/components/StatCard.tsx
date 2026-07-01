import React from 'react';

interface StatCardProps {
  title: string;
  value: string | number;
  suffix?: string;
  icon?: React.ReactNode;
  loading?: boolean;
  onClick?: () => void;
  bordered?: boolean;
}

export default function StatCard({
  title,
  value,
  suffix,
  icon,
  loading = false,
  onClick,
  bordered = true,
}: StatCardProps) {
  return (
    <div
      className="stat-card"
      onClick={onClick}
      style={{
        background: 'var(--card-bg)',
        border: bordered ? '1px solid var(--card-border)' : 'none',
        borderRadius: 'var(--card-radius)',
        padding: '24px',
        boxShadow: 'var(--shadow-card)',
        transition: 'border-color var(--transition-fast), background var(--transition-fast), box-shadow var(--transition-fast)',
        cursor: onClick ? 'pointer' : 'default',
        position: 'relative',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = 'var(--border-hover)';
        e.currentTarget.style.background = 'var(--bg-elevated)';
        e.currentTarget.style.boxShadow = 'var(--shadow-card-hover)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--card-border)';
        e.currentTarget.style.background = 'var(--card-bg)';
        e.currentTarget.style.boxShadow = 'var(--shadow-card)';
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div style={{ flex: 1 }}>
          <div
            className="stat-title"
            style={{
              fontSize: 'var(--text-label-size)',
              color: 'var(--text-tertiary)',
              fontWeight: 500,
              marginBottom: '14px',
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
            }}
          >
            {title}
          </div>
          {loading ? (
            <div
              style={{
                height: '36px',
                width: '80px',
                background: 'var(--bg-hover)',
                borderRadius: 'var(--radius-md)',
                animation: 'pulse 1.5s ease-in-out infinite',
              }}
            />
          ) : (
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
              <span
                className="stat-value tabular-nums"
                style={{
                  fontSize: 'var(--text-data-xl-size)',
                  fontWeight: 400,
                  color: 'var(--text-primary)',
                  lineHeight: 1.1,
                  fontFamily: 'var(--font-mono)',
                  letterSpacing: '-0.02em',
                }}
              >
                {value}
              </span>
              {suffix && (
                <span
                  className="stat-suffix"
                  style={{
                    fontSize: 'var(--text-small-size)',
                    color: 'var(--text-tertiary)',
                    fontWeight: 500,
                  }}
                >
                  {suffix}
                </span>
              )}
            </div>
          )}
        </div>
        {icon && (
          <div
            className="stat-icon"
            style={{
              width: '44px',
              height: '44px',
              borderRadius: 'var(--radius-lg)',
              background: 'var(--accent-dim)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '20px',
              flexShrink: 0,
              marginLeft: '12px',
              color: 'var(--accent)',
            }}
          >
            {icon}
          </div>
        )}
      </div>
    </div>
  );
}
