import { useState } from 'react';
import { Grid } from 'antd';

/**
 * 基于 Ant Design 栅格断点的响应式 hook。
 * xs: <576px, sm: ≥576px, md: ≥768px, lg: ≥992px, xl: ≥1200px, xxl: ≥1600px
 */
export function useBreakpoint() {
  return Grid.useBreakpoint();
}

/** matchMedia 同步求值（带环境守卫，jsdom / SSR 下安全回落 false） */
function queryMobile(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }
  return window.matchMedia('(max-width: 767px)').matches;
}

/**
 * 判断当前是否为移动端（<768px）。
 * 用于全局布局、抽屉菜单、卡片化表格等场景。
 */
export function useIsMobile() {
  const screens = useBreakpoint();
  // antd Grid 断点首帧为空对象，直接回落 false 会让移动端首帧闪出桌面侧边栏。
  // 用 matchMedia 同步求值作为初始值，断点就绪后交给 antd screens 驱动。
  const [initialMobile] = useState(queryMobile);
  if (!screens || Object.keys(screens).length === 0) return initialMobile;
  return Boolean(screens.xs || (screens.sm && !screens.md));
}

/**
 * 判断当前是否为平板/小桌面（<992px）。
 * 用于侧边栏自动折叠等场景。
 */
export function useIsTablet() {
  const screens = useBreakpoint();
  if (!screens || Object.keys(screens).length === 0) return false;
  return Boolean(screens.xs || screens.sm || (screens.md && !screens.lg));
}
