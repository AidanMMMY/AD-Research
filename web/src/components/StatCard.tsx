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
      className={`stat-card ${onClick ? 'stat-card--clickable' : ''}`}
      onClick={onClick}
      style={{ border: bordered ? undefined : 'none' }}
    >
      <div className="stat-card__inner">
        <div className="stat-card__main">
          <div className="stat-card__title">{title}</div>
          {loading ? (
            <div className="stat-card__skeleton" />
          ) : (
            <div className="stat-card__value-row">
              <span className="stat-card__value tabular-nums">{value}</span>
              {suffix && <span className="stat-card__suffix">{suffix}</span>}
            </div>
          )}
        </div>
        {icon && <div className="stat-card__icon">{icon}</div>}
      </div>
    </div>
  );
}
