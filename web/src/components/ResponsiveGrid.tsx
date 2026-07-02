import React from 'react';

export interface ResponsiveGridProps {
  children: React.ReactNode;
  cols?: 1 | 2 | 3 | 4;
  gap?: 'sm' | 'md' | 'lg';
  className?: string;
}

export default function ResponsiveGrid({
  children,
  cols = 1,
  gap = 'md',
  className,
}: ResponsiveGridProps) {
  return (
    <div
      className={`responsive-grid responsive-grid--cols-${cols} responsive-grid--gap-${gap} ${
        className || ''
      }`.trim()}
    >
      {children}
    </div>
  );
}
