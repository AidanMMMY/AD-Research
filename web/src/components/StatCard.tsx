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
        background: 'transparent',
        border: bordered ? '1px solid var(--border-default)' : 'none',
        borderRadius: 0,
        padding: '20px',
        transition: 'border-color var(--transition-fast), background var(--transition-fast)',
        cursor: onClick ? 'pointer' : 'default',
        position: 'relative',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = 'var(--border-hover)';
        e.currentTarget.style.background = 'var(--bg-hover)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--border-default)';
        e.currentTarget.style.background = 'transparent';
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
              marginBottom: '10px',
              letterSpacing: '0.08em',
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
                borderRadius: '4px',
                animation: 'pulse 1.5s ease-in-out infinite',
              }}
            />
          ) : (
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
              <span
                className="stat-value"
                style={{
                  fontSize: 'var(--text-data-lg-size)',
                  fontWeight: 400,
                  color: 'var(--text-primary)',
                  lineHeight: 1.2,
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
              width: '40px',
              height: '40px',
              borderRadius: 'var(--radius-md)',
              background: 'var(--bg-input)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '18px',
              flexShrink: 0,
              marginLeft: '12px',
              color: 'var(--accent)',
              border: '1px solid var(--border-default)',
            }}
          >
            {icon}
          </div>
        )}
      </div>
    </div>
  );
}
