import { Grid } from 'antd';

/**
 * 基于 Ant Design 栅格断点的响应式 hook。
 * xs: <576px, sm: ≥576px, md: ≥768px, lg: ≥992px, xl: ≥1200px, xxl: ≥1600px
 */
export function useBreakpoint() {
  return Grid.useBreakpoint();
}

/**
 * 判断当前是否为移动端（<768px）。
 * 用于全局布局、抽屉菜单、卡片化表格等场景。
 */
export function useIsMobile() {
  const screens = useBreakpoint();
  // 初始服务端渲染/断点未计算完成时保守返回 false，避免布局闪烁
  if (!screens || Object.keys(screens).length === 0) return false;
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
