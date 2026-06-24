import React from 'react';

interface GradientStatCardProps {
  title: string;
  value: string | number;
  suffix?: string;
  icon?: React.ReactNode;
  gradient?: 'purple' | 'cyan' | 'green' | 'orange' | 'pink';
  loading?: boolean;
  onClick?: () => void;
}

const gradientMap = {
  purple: 'linear-gradient(135deg, rgba(99,102,241,0.2) 0%, rgba(139,92,246,0.15) 100%)',
  cyan: 'linear-gradient(135deg, rgba(6,182,212,0.2) 0%, rgba(20,184,166,0.15) 100%)',
  green: 'linear-gradient(135deg, rgba(34,197,94,0.2) 0%, rgba(132,204,22,0.15) 100%)',
  orange: 'linear-gradient(135deg, rgba(249,115,22,0.2) 0%, rgba(234,179,8,0.15) 100%)',
  pink: 'linear-gradient(135deg, rgba(236,72,153,0.2) 0%, rgba(168,85,247,0.15) 100%)',
};

const glowMap = {
  purple: '0 0 20px rgba(99,102,241,0.15)',
  cyan: '0 0 20px rgba(6,182,212,0.15)',
  green: '0 0 20px rgba(34,197,94,0.15)',
  orange: '0 0 20px rgba(249,115,22,0.15)',
  pink: '0 0 20px rgba(236,72,153,0.15)',
};

const iconBgMap = {
  purple: 'rgba(99,102,241,0.15)',
  cyan: 'rgba(6,182,212,0.15)',
  green: 'rgba(34,197,94,0.15)',
  orange: 'rgba(249,115,22,0.15)',
  pink: 'rgba(236,72,153,0.15)',
};

export default function GradientStatCard({
  title,
  value,
  suffix,
  icon,
  gradient = 'purple',
  loading = false,
  onClick,
}: GradientStatCardProps) {
  return (
    <div
      className="gradient-stat-card"
      onClick={onClick}
      style={{
        background: gradientMap[gradient],
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        border: '1px solid rgba(255, 255, 255, 0.08)',
        borderRadius: '16px',
        padding: '24px',
        boxShadow: glowMap[gradient],
        transition: 'all 250ms cubic-bezier(0.4, 0, 0.2, 1)',
        cursor: onClick ? 'pointer' : 'default',
        position: 'relative',
        overflow: 'hidden',
      }}
      onMouseEnter={(e) => {
        const el = e.currentTarget;
        el.style.borderColor = 'rgba(255, 255, 255, 0.15)';
        el.style.transform = 'translateY(-3px)';
        el.style.boxShadow = glowMap[gradient].replace('0.15', '0.3');
      }}
      onMouseLeave={(e) => {
        const el = e.currentTarget;
        el.style.borderColor = 'rgba(255, 255, 255, 0.08)';
        el.style.transform = 'translateY(0)';
        el.style.boxShadow = glowMap[gradient];
      }}
    >
      {/* Top-right decorative circle */}
      <div
        className="gradient-stat-decor"
        style={{
          position: 'absolute',
          top: '-20px',
          right: '-20px',
          width: '80px',
          height: '80px',
          borderRadius: '50%',
          background: gradientMap[gradient].replace(/0\.[0-9]+/g, '0.08'),
          filter: 'blur(20px)',
          pointerEvents: 'none',
        }}
      />

      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div style={{ flex: 1 }}>
          <div
            className="gradient-stat-title"
            style={{
              fontSize: '13px',
              color: '#94a3b8',
              fontWeight: 400,
              marginBottom: '10px',
              letterSpacing: '0.5px',
            }}
          >
            {title}
          </div>
          {loading ? (
            <div
              style={{
                height: '36px',
                width: '80px',
                background: 'rgba(255,255,255,0.05)',
                borderRadius: '6px',
                animation: 'pulse 1.5s ease-in-out infinite',
              }}
            />
          ) : (
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
              <span
                className="gradient-stat-value"
                style={{
                  fontSize: '32px',
                  fontWeight: 700,
                  color: '#f1f5f9',
                  lineHeight: 1.2,
                  fontFamily:
                    "'SF Mono', 'Fira Code', 'Cascadia Code', -apple-system, sans-serif",
                  letterSpacing: '-0.5px',
                }}
              >
                {value}
              </span>
              {suffix && (
                <span
                  className="gradient-stat-suffix"
                  style={{
                    fontSize: '14px',
                    color: '#64748b',
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
            className="gradient-stat-icon"
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '12px',
              background: iconBgMap[gradient],
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '20px',
              flexShrink: 0,
              marginLeft: '12px',
            }}
          >
            {icon}
          </div>
        )}
      </div>
    </div>
  );
}
