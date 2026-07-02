import React from 'react';

export interface PageShellProps {
  children: React.ReactNode;
  maxWidth?: 'reading' | 'wide' | 'full';
  className?: string;
}

export default function PageShell({
  children,
  maxWidth = 'wide',
  className,
}: PageShellProps) {
  const widthClass =
    maxWidth === 'reading'
      ? 'page-shell--reading'
      : maxWidth === 'wide'
      ? 'page-shell--wide'
      : 'page-shell--full';

  return (
    <div className={`page-shell ${widthClass} ${className || ''}`.trim()}>
      {children}
    </div>
  );
}
