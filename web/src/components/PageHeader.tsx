import React from 'react';

/**
 * Standardized page header used at the top of every primary page.
 *
 *   <PageHeader
 *     eyebrow="ETF投研"
 *     title="评分排名"
 *     description="查看全市场标的综合评分排名..."
 *     extra={<Button>导出</Button>}
 *   />
 *
 * Replaces the ad-hoc `<h1 style={{...}}>` + `<p style={{...}}>` pairs that
 * were duplicated across pages with subtly different margins / sizes.
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
}

export default function PageHeader({
  eyebrow,
  title,
  description,
  extra,
  breadcrumb,
  compact = false,
}: PageHeaderProps) {
  return (
    <header className="page-header" data-compact={compact || undefined}>
      {breadcrumb ? (
        <div className="page-header-breadcrumb">{breadcrumb}</div>
      ) : null}
      <div className="page-header-row">
        <div className="page-header-text">
          {eyebrow ? <div className="page-header-eyebrow">{eyebrow}</div> : null}
          <h1 className="page-header-title">{title}</h1>
          {description ? <p className="page-header-description">{description}</p> : null}
        </div>
        {extra ? <div className="page-header-extra">{extra}</div> : null}
      </div>
    </header>
  );
}