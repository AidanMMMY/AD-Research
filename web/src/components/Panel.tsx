import React from 'react';

export type PanelVariant = 'default' | 'minimal' | 'transparent';

/**
 * 通用内容面板 — 薄封装 card surface，Phase 2 (2026-07-05) 起全面 token 化。
 *
 * - 颜色 / 间距 / 圆角 / 边框 全部走 CSS 变量，light/dark 自动跟随。
 * - 通过 `--padding` 调节内部留白（none/sm/md/lg），移动端自动收紧。
 * - `--variant` 控制外观：`default` 卡片化 / `minimal` 仅保留 header 分隔线 / `transparent` 全透明。
 *
 *   <Panel title="..." extra={<Tag>X</Tag>} padding="md">
 *     {children}
 *   </Panel>
 */
export interface PanelProps {
  children: React.ReactNode;
  title?: React.ReactNode;
  extra?: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  variant?: PanelVariant;
  padding?: 'none' | 'sm' | 'md' | 'lg';
}

export default function Panel({
  children,
  title,
  extra,
  className = '',
  style,
  variant = 'default',
  padding = 'md',
}: PanelProps) {
  const classes = [
    'ad-panel',
    `ad-panel--${variant}`,
    `ad-panel--padding-${padding}`,
    className,
  ]
    .filter(Boolean)
    .join(' ');

  const showHeader = Boolean(title || extra);

  return (
    <div className={classes} style={style}>
      {showHeader ? (
        <div className="ad-panel__header">
          {title ? <span className="ad-panel__title">{title}</span> : null}
          {extra ? <div className="ad-panel__extra">{extra}</div> : null}
        </div>
      ) : null}
      <div className="ad-panel__body">{children}</div>
    </div>
  );
}