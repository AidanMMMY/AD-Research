import React from 'react';

export interface FilterToolbarProps {
  /** Filters / controls rendered on the left. Optional — empty meta-only
   *  toolbars (e.g. PoolList total) are valid. */
  children?: React.ReactNode;
  total?: number | string;
  extra?: React.ReactNode;
  /** Optional title shown in the toolbar header row, left of the meta. */
  title?: React.ReactNode;
  /** Optional className forwarded to the wrapping div. Phase 2 (2026-07-05)
   *  added this for `className="ad-mb-5"` style spacing helpers in pages. */
  className?: string;
  /** Forwarded to the wrapping div. M19 P1 uses this for `data-onboard`. */
  'data-onboard'?: string;
}

export default function FilterToolbar({
  children,
  total,
  extra,
  title,
  className,
  ...rest
}: FilterToolbarProps) {
  const showMeta = total !== undefined || extra !== undefined;
  const wrapperClass = ['filter-toolbar', title !== undefined ? 'filter-toolbar--headed' : '', className]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={wrapperClass} {...rest}>
      {title !== undefined ? (
        <div className="filter-toolbar__header">
          <div className="filter-toolbar__title">{title}</div>
          {showMeta ? (
            <div className="filter-toolbar__meta">
              {total !== undefined ? (
                <span className="filter-toolbar__total">
                  {typeof total === 'number' ? total.toLocaleString() : total}
                </span>
              ) : null}
              {extra}
            </div>
          ) : null}
        </div>
      ) : null}
      {children !== undefined ? (
        <div className="filter-toolbar__filters">{children}</div>
      ) : null}
      {title === undefined && showMeta ? (
        <div className="filter-toolbar__meta">
          {total !== undefined ? (
            <span className="filter-toolbar__total">
              {typeof total === 'number' ? total.toLocaleString() : total}
            </span>
          ) : null}
          {extra}
        </div>
      ) : null}
    </div>
  );
}
