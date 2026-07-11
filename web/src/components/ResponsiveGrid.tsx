import React from 'react';

export interface ResponsiveGridProps {
  children: React.ReactNode;
  cols?: 1 | 2 | 3 | 4;
  gap?: 'sm' | 'md' | 'lg';
  className?: string;
  /** Stretch children to equal height (default: false).
   *  Adds the `responsive-grid--stretch` modifier which makes
   *  each direct child fill the row's tallest item. */
  stretch?: boolean;
}

export default function ResponsiveGrid({
  children,
  cols = 1,
  gap = 'md',
  className,
  stretch = false,
}: ResponsiveGridProps) {
  const stretchClass = stretch ? ' responsive-grid--stretch' : '';
  return (
    <div
      className={`responsive-grid responsive-grid--cols-${cols} responsive-grid--gap-${gap}${
        stretchClass
      } ${className || ''}`.trim()}
    >
      {children}
    </div>
  );
}
