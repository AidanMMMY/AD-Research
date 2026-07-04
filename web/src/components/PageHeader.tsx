import React from 'react';
import { useSettingsStore } from '@/stores/settings';

/**
 * Standardized page header used at the top of every primary page.
 *
 *   <PageHeader
 *     eyebrow="ETF投研"
 *     title="评分排名"
 *     description="查看全市场标的综合评分排名..."
 *     tutorial={<span>...</span>}     // K15: 新手教学"怎么读这个页"
 *     extra={<Button>导出</Button>}
 *   />
 *
 * Phase 2 (2026-07-05): 字号 / 间距全部走 token (`--text-h1-size` / `--space-5` /
 * `--text-body-size`)，`data-compact` 控制详情页紧凑变体。
 */
export interface PageHeaderProps {
  /** Optional eyebrow label above the title (small uppercase). */
  eyebrow?: React.ReactNode;
  /** Main H1. Required. */
  title: React.ReactNode;
  /** One-sentence tagline below the title. */
  description?: React.ReactNode;
  /** Right-aligned slot for primary actions / controls. */
  extra?: React.ReactNode;
  /** Optional breadcrumb-like path rendered above the eyebrow. */
  breadcrumb?: React.ReactNode;
  /** Compact variant — used on tabs / detail sub-pages where vertical space is tight. */
  compact?: boolean;
  /**
   * K15: 新手教学槽。1-3 句话说明"怎么读这个页面"。
   * 当 useSettingsStore().mode === 'novice' 时显示，或当页面显式传入时常驻。
   */
  tutorial?: React.ReactNode;
  /** 强制教学槽显隐，覆盖 settings.mode 默认行为。 */
  tutorialForce?: boolean;
  /** Forwarded to the wrapping header for onboarding tour anchoring (M19 P1). */
  'data-onboard'?: string;
}

export default function PageHeader({
  eyebrow,
  title,
  description,
  extra,
  breadcrumb,
  compact = false,
  tutorial,
  tutorialForce,
  ...rest
}: PageHeaderProps) {
  // K15: 默认依据 settings.mode：novice 时显示；显式传 tutorialForce 可覆盖。
  const settingsMode = useSettingsStore((s) => s.mode);
  const showTutorial = tutorialForce ?? (settingsMode === 'novice' && !!tutorial);

  return (
    <header className="page-header" data-compact={compact || undefined} {...rest}>
      {breadcrumb ? (
        <div className="page-header-breadcrumb">{breadcrumb}</div>
      ) : null}
      <div className="page-header-row">
        <div className="page-header-text">
          {eyebrow ? <div className="page-header-eyebrow">{eyebrow}</div> : null}
          <h1 className="page-header-title">{title}</h1>
          {description ? <p className="page-header-description">{description}</p> : null}
          {showTutorial && tutorial ? (
            <div className="page-header-tutorial">{tutorial}</div>
          ) : null}
        </div>
        {extra ? <div className="page-header-extra">{extra}</div> : null}
      </div>
    </header>
  );
}