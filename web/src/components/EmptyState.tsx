import React from 'react';

export interface EmptyStateProps {
  icon?: React.ReactNode;
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
}

export default function EmptyState({
  icon,
  title,
  description,
  action,
  className,
  style,
}: EmptyStateProps) {
  return (
    <div className={`empty-state ${className ?? ''}`} style={style}>
      {icon ? (
        <div className="empty-state__icon-area">
          <span className="empty-state__icon">{icon}</span>
        </div>
      ) : null}
      <h3 className="empty-state__title">{title}</h3>
      {description ? (
        <p className="empty-state__description">{description}</p>
      ) : null}
      {action ? <div className="empty-state__action">{action}</div> : null}
    </div>
  );
}
