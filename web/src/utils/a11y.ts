import type React from 'react';

export interface AccessibleRowProps {
  tabIndex?: number;
  role?: string;
  onKeyDown?: React.KeyboardEventHandler<HTMLTableRowElement>;
}

/**
 * 把 Table onRow 返回的 `{ onClick: ... }` 对象包装成可键盘访问的行。
 * 自动添加 tabIndex=0、role="link"、以及 Enter/Space 触发 onClick 的 onKeyDown。
 * 在 onClick 不存在时原样返回，避免影响没有交互行为的行。
 */
export function clickableRow(
  onClick: (() => void) | ((e: React.MouseEvent<HTMLTableRowElement>) => void),
  { tabIndex = 0, role = 'link' }: Partial<AccessibleRowProps> = {},
): Record<string, any> {
  return {
    tabIndex,
    role,
    onClick,
    onKeyDown: (e: React.KeyboardEvent<HTMLTableRowElement>) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onClick(e as unknown as React.MouseEvent<HTMLTableRowElement>);
      }
    },
  };
}

/**
 * 为交互式元素补齐 keyboard/role/tabIndex 支持，常用于 span 模拟的按钮。
 */
export function clickableProps(
  onClick: React.MouseEventHandler<HTMLElement>,
  options: { role?: string; tabIndex?: number; onKeyDown?: React.KeyboardEventHandler<HTMLElement> } = {},
): Record<string, any> {
  const { role = 'button', tabIndex = 0, onKeyDown } = options;
  return {
    role,
    tabIndex,
    onClick,
    onKeyDown: (e: React.KeyboardEvent<HTMLElement>) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onClick(e as unknown as React.MouseEvent<HTMLElement>);
      }
      onKeyDown?.(e);
    },
  };
}

/**
 * 通用图表容器 aria 属性，供 canvas/echarts 等无文字图表使用。
 */
export function chartA11yProps(
  label: string,
): { role: 'img'; 'aria-label': string } {
  return { role: 'img', 'aria-label': label };
}
