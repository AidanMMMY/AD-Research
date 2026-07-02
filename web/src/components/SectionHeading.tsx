import React from 'react';

export interface SectionHeadingProps {
  title: React.ReactNode;
  eyebrow?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

export default function SectionHeading({
  title,
  eyebrow,
  action,
  className,
}: SectionHeadingProps) {
  return (
    <div className={`ad-section-heading ${className || ''}`.trim()}>
      <div>
        {eyebrow ? (
          <div className="ad-section-heading__eyebrow">{eyebrow}</div>
        ) : null}
        <h2 className="ad-section-heading__title">{title}</h2>
      </div>
      {action ? (
        <div className="ad-section-heading__action">{action}</div>
      ) : null}
    </div>
  );
}
