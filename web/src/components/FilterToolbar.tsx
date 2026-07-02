import React from 'react';

export interface FilterToolbarProps {
  children: React.ReactNode;
  total?: number | string;
  extra?: React.ReactNode;
}

export default function FilterToolbar({
  children,
  total,
  extra,
}: FilterToolbarProps) {
  const showMeta = total !== undefined || extra !== undefined;

  return (
    <div className="filter-toolbar">
      <div className="filter-toolbar__filters">{children}</div>
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
