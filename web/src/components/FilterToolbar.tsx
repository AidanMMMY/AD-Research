import React from 'react';

export interface FilterToolbarProps {
  /** Filters / controls rendered on the left. Optional — empty meta-only
   *  toolbars (e.g. PoolList total) are valid. */
  children?: React.ReactNode;
  total?: number | string;
  extra?: React.ReactNode;
  /** Forwarded to the wrapping div. M19 P1 uses this for `data-onboard`. */
  'data-onboard'?: string;
}

export default function FilterToolbar({
  children,
  total,
  extra,
  ...rest
}: FilterToolbarProps) {
  const showMeta = total !== undefined || extra !== undefined;

  return (
    <div className="filter-toolbar" {...rest}>
      {children !== undefined ? (
        <div className="filter-toolbar__filters">{children}</div>
      ) : null}
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
  );
}
