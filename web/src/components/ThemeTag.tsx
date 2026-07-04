import React from 'react';
import { Tag } from 'antd';

export type ThemeTagVariant =
  | 'default'
  | 'accent'
  | 'rise'
  | 'fall'
  | 'success'
  | 'error'
  | 'warning'
  | 'neutral';

interface ThemeTagProps {
  variant?: ThemeTagVariant;
  children: React.ReactNode;
  icon?: React.ReactNode;
  style?: React.CSSProperties;
  className?: string;
  title?: string;
  onClick?: React.MouseEventHandler<HTMLSpanElement>;
}

/**
 * 主题化 Tag — 不使用 Ant Design 预设色，全部基于 design token。
 */
export default function ThemeTag({
  variant = 'default',
  children,
  icon,
  style,
  className,
  title,
  onClick,
}: ThemeTagProps) {
  const classes = className
    ? `theme-tag theme-tag--${variant} ${className}`
    : `theme-tag theme-tag--${variant}`;

  return (
    <Tag className={classes} icon={icon} title={title} onClick={onClick} style={style}>
      {children}
    </Tag>
  );
}
