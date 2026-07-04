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
 * 主题化 Tag — 不使用 Ant Design 预设色，全部基于 design token
 * (`--accent` / `--color-rise` / `--color-fall` / `--color-success` …)。
 *
 * Phase 2 (2026-07-05): 重写为 class-only（保留 `style` 透传以便覆盖动态值）。
 * 颜色 / 间距 / 圆角 / 边框 全部 token 化，light/dark + China/US 自动跟随。
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
  const classes = [
    'theme-tag',
    `theme-tag--${variant}`,
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <Tag className={classes} icon={icon} title={title} onClick={onClick} style={style}>
      {children}
    </Tag>
  );
}