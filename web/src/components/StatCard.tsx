import React from 'react';
import StatExplainer from '@/components/StatExplainer';

interface StatCardProps {
  title: string | React.ReactNode;
  value: string | number | React.ReactNode;
  suffix?: string;
  icon?: React.ReactNode;
  loading?: boolean;
  onClick?: () => void;
  bordered?: boolean;
  /**
   * K15: 学习模式下挂的"一句话解释"term key。
   * 与 <StatExplainer termKey> 等价，仅挂在 StatCard 内置位置上。
   */
  term?: string;
  /** 自定义解释文本，覆盖 term.shortDesc */
  explainer?: string;
}

export default function StatCard({
  title,
  value,
  suffix,
  icon,
  loading = false,
  onClick,
  bordered = true,
  term,
  explainer,
}: StatCardProps) {
  return (
    <div
      className={`stat-card ${onClick ? 'stat-card--clickable' : ''} ${bordered ? '' : 'stat-card--borderless'}`}
      onClick={onClick}
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
          {/* K15: 学习模式下的伴随式解释。term 未传时不渲染。 */}
          {(term || explainer) && (
            <StatExplainer termKey={term} text={explainer} className="stat-card__explainer" />
          )}
        </div>
        {icon && <div className="stat-card__icon">{icon}</div>}
      </div>
    </div>
  );
}
