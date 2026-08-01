import React from 'react';
import StatExplainer from '@/components/StatExplainer';

interface StatCardProps {
  title: string | React.ReactNode;
  value: string | number | React.ReactNode;
  suffix?: string;
  icon?: React.ReactNode;
  loading?: boolean;
  onClick?: () => void;
  /**
   * K15: 学习模式下挂的"一句话解释"term key。
   * 与 <StatExplainer termKey> 等价，仅挂在 StatCard 内置位置上。
   */
  term?: string;
  /** 自定义解释文本，覆盖 term.shortDesc */
  explainer?: string;
}

/**
 * KPI 数字卡 — Phase 2 (2026-07-05) 起 hover 改用 CSS (`.stat-card:hover`)，
 * 不再走 inline `onMouseEnter/Leave` DOM 操作。颜色 / 间距 / 圆角 / 字号
 * 全部走 token，dark 主题下边框 / 阴影自动切换。
 *
 * 2026-08-01：`bordered` prop 已删除 — a36fe23 起 `.stat-card` 默认就是
 * hairline 无 chrome，`stat-card--borderless` 成为无效果的死代码。
 */
export default function StatCard({
  title,
  value,
  suffix,
  icon,
  loading = false,
  onClick,
  term,
  explainer,
}: StatCardProps) {
  // a11y: when clickable, the card must be reachable by keyboard
  // (review-a11y-mobile P0-2). role="button" + tabIndex=0 + Enter/Space.
  const isClickable = Boolean(onClick);
  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!isClickable) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onClick?.();
    }
  };
  return (
    <div
      className={`stat-card ${isClickable ? 'stat-card--clickable' : ''}`}
      onClick={onClick}
      role={isClickable ? 'button' : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onKeyDown={handleKeyDown}
      aria-label={
        isClickable && (typeof title === 'string' || typeof title === 'number')
          ? `${title}: ${value}`
          : undefined
      }
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