/* Phase 3 (2026-07-05) rewrite of the app shell.
 *
 * Goals for this rewrite:
 *   • Sidebar 240 / 72 (kept from Phase 2)
 *   • Header 60px sticky, var(--bg-base), hairline bottom border,
 *     NO dark-glass backdrop-filter (the M28 refresh added one — we
 *     strip it here; see AppLayout.css override)
 *   • Collapse toggle moves from the bottom of the sidebar to the
 *     top-right of the header (Phase 3 spec)
 *   • Theme (light/dark) and color-convention (China/US) toggles
 *     live in the header right cluster
 *   • Mobile <768px: sidebar is hidden, drawer takes over with a
 *     hamburger trigger at the header left
 *   • All existing routing, breadcrumb, onboarding, density
 *     toggle, learning-mode hint, etc. preserved
 */
import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { Dropdown, Drawer, Segmented, Tooltip } from 'antd';
import {
  LogoutOutlined,
  DashboardOutlined,
  OrderedListOutlined,
  FilterOutlined,
  AppstoreOutlined,
  TrophyOutlined,
  FileTextOutlined,
  ApartmentOutlined,
  LineChartOutlined,
  BarChartOutlined,
  ScanOutlined,
  NotificationOutlined,
  SettingOutlined,
  ExperimentOutlined,
  ThunderboltOutlined,
  TeamOutlined,
  ReadOutlined,
  HeartOutlined,
  RobotOutlined,
  CloudServerOutlined,
  GoldOutlined,
  DollarOutlined,
  MonitorOutlined,
  BookOutlined,
  CalendarOutlined,
  ClockCircleOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MenuOutlined,
  HomeOutlined,
  RightOutlined,
  DownOutlined,
  BankOutlined,
  FundOutlined,
  FireOutlined,
  FilePdfOutlined,
  BlockOutlined,
  SunOutlined,
  MoonOutlined,
  BulbOutlined,
  CompassOutlined,
  FundProjectionScreenOutlined,
  BellOutlined,
  ToolOutlined,
  SafetyCertificateOutlined,
  WalletOutlined,
} from '@ant-design/icons';
import { Switch, message } from 'antd';
import { useAuthStore } from '@/stores/auth';
import { useSettingsStore } from '@/stores/settings';
import { menuRoutes, sidebarGroups, type SidebarGroupKey } from '@/routes';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { useTheme, type Theme } from '@/hooks/useTheme';
import DensityToggle from '@/components/DensityToggle';
import OnboardingTour from '@/components/OnboardingTour';
import './AppLayout.css';

const iconMap: Record<string, React.ComponentType> = {
  DashboardOutlined,
  OrderedListOutlined,
  FilterOutlined,
  AppstoreOutlined,
  TrophyOutlined,
  FileTextOutlined,
  ApartmentOutlined,
  LineChartOutlined,
  BarChartOutlined,
  ScanOutlined,
  NotificationOutlined,
  SettingOutlined,
  ExperimentOutlined,
  ThunderboltOutlined,
  TeamOutlined,
  ReadOutlined,
  HeartOutlined,
  RobotOutlined,
  CloudServerOutlined,
  GoldOutlined,
  DollarOutlined,
  MonitorOutlined,
  BookOutlined,
  CalendarOutlined,
  ClockCircleOutlined,
  BankOutlined,
  FundOutlined,
  FireOutlined,
  FilePdfOutlined,
  BlockOutlined,
  HomeOutlined,
  CompassOutlined,
  FundProjectionScreenOutlined,
  BellOutlined,
  ToolOutlined,
  SafetyCertificateOutlined,
  WalletOutlined,
};

const SIDEBAR_EXPANDED_KEY = 'ad-research:sidebar:expanded';

function loadExpandedGroups(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(SIDEBAR_EXPANDED_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function persistExpandedGroups(state: Record<string, boolean>) {
  try {
    localStorage.setItem(SIDEBAR_EXPANDED_KEY, JSON.stringify(state));
  } catch {
    /* swallow storage errors (e.g. SSR / quota) */
  }
}

interface SidebarContentProps {
  collapsed: boolean;
  onItemClick?: () => void;
}

/* ------------------------------------------------------------
 * SidebarContent — the 1-level group + 2-level collapsible nav.
 * Logic preserved verbatim from the M28 refresh; only the
 * surrounding shell changed in Phase 3.
 * ------------------------------------------------------------ */
function SidebarContent({ collapsed, onItemClick }: SidebarContentProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';

  // Group menu items by their `group` field, preserving sidebarGroups ordering.
  const groupedItems = useMemo(() => {
    const map = new Map<SidebarGroupKey, typeof menuRoutes>();
    for (const route of menuRoutes) {
      const group = route.menu?.group;
      if (!group) continue;
      if (group === 'admin' && !isAdmin) continue;
      if (!map.has(group)) map.set(group, []);
      map.get(group)!.push(route);
    }
    return sidebarGroups
      .filter((g) => map.has(g.key))
      .map((g) => ({ group: g, items: map.get(g.key)! }));
  }, [isAdmin]);

  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    const stored = loadExpandedGroups();
    const initial: Record<string, boolean> = {};
    for (const { group, items } of groupedItems) {
      const hasActive = items.some(
        (r) => location.pathname === r.path || location.pathname.startsWith(r.path + '/')
      );
      if (hasActive) {
        initial[group.key] = true;
      } else if (stored[group.key] !== undefined) {
        initial[group.key] = stored[group.key];
      } else {
        initial[group.key] = false;
      }
    }
    return initial;
  });

  useEffect(() => {
    persistExpandedGroups(expanded);
  }, [expanded]);

  useEffect(() => {
    setExpanded((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const { group, items } of groupedItems) {
        const hasActive = items.some(
          (r) => location.pathname === r.path || location.pathname.startsWith(r.path + '/')
        );
        if (hasActive && !next[group.key]) {
          next[group.key] = true;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [location.pathname, groupedItems]);

  const toggleGroup = useCallback((key: string) => {
    setExpanded((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  return (
    <>
      {/* Logo */}
      <div className="app-layout__logo">
        <div className="app-layout__logo-mark" aria-hidden="true">E</div>
        {!collapsed && <span className="app-layout__logo-text">投研平台</span>}
      </div>

      {/* Menu Items — grouped 1-level + 2-level collapsible */}
      <nav className="app-layout__nav" aria-label="主导航">
        {groupedItems.map(({ group, items }) => {
          const GroupIcon = iconMap[group.icon];
          const isOpen = !!expanded[group.key];
          const groupHasActive = items.some(
            (r) => location.pathname === r.path || location.pathname.startsWith(r.path + '/')
          );
          const groupHeaderId = `sidebar-group-${group.key}`;

          return (
            <div
              key={group.key}
              className={`app-layout__nav-group ${isOpen ? 'is-open' : 'is-collapsed'} ${
                groupHasActive ? 'has-active' : ''
              }`}
            >
              {!collapsed && (
                <div
                  role="button"
                  tabIndex={0}
                  aria-expanded={isOpen}
                  aria-controls={groupHeaderId}
                  className="app-layout__nav-group-header"
                  onClick={() => toggleGroup(group.key)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      toggleGroup(group.key);
                    }
                  }}
                >
                  {GroupIcon && (
                    <span className="app-layout__nav-group-icon" aria-hidden="true">
                      <GroupIcon />
                    </span>
                  )}
                  <span className="app-layout__nav-group-label">{group.label}</span>
                  <span
                    className={`app-layout__nav-group-chevron ${isOpen ? 'is-open' : ''}`}
                    aria-hidden="true"
                  >
                    <DownOutlined />
                  </span>
                </div>
              )}
              {collapsed ? (
                <div
                  className="app-layout__nav-item"
                  role="button"
                  tabIndex={0}
                  aria-label={`${group.label}（展开侧边栏查看子菜单）`}
                  onClick={() => {
                    const first = items[0];
                    if (first) {
                      navigate(first.path);
                      onItemClick?.();
                    }
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      const first = items[0];
                      if (first) {
                        navigate(first.path);
                        onItemClick?.();
                      }
                    }
                  }}
                >
                  {GroupIcon && (
                    <span className="app-layout__nav-icon">
                      <GroupIcon />
                    </span>
                  )}
                </div>
              ) : (
                <div
                  id={groupHeaderId}
                  className="app-layout__nav-group-items"
                  role="region"
                  aria-label={`${group.label} 子菜单`}
                  hidden={!isOpen}
                >
                  {items.map((route) => {
                    const isActive =
                      location.pathname === route.path ||
                      location.pathname.startsWith(route.path + '/');
                    const Icon = route.menu?.icon ? iconMap[route.menu.icon] : null;
                    const label = route.menu?.label || route.menu?.name || '';
                    return (
                      <div
                        key={route.path}
                        role="button"
                        tabIndex={0}
                        aria-current={isActive ? 'page' : undefined}
                        className={`app-layout__nav-item ${isActive ? 'app-layout__nav-item--active' : ''}`}
                        onClick={() => {
                          navigate(route.path);
                          onItemClick?.();
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            navigate(route.path);
                            onItemClick?.();
                          }
                        }}
                      >
                        {Icon && (
                          <span className="app-layout__nav-icon">
                            <Icon />
                          </span>
                        )}
                        <span className="app-layout__nav-label">{label}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>
    </>
  );
}

/* ------------------------------------------------------------
 * ThemeToggle — header control for light/dark.  Phase 3 spec
 * says no flash on switch, so the toggle writes to useTheme
 * synchronously (the existing Phase 1 main.tsx subscriber
 * applies the data-theme attribute on the same tick).
 * ------------------------------------------------------------ */
interface ThemeToggleProps {
  theme: Theme;
  onChange: (t: Theme) => void;
}

function ThemeToggle({ theme, onChange }: ThemeToggleProps) {
  return (
    <Tooltip title={theme === 'light' ? '当前：浅色 · 点击切换深色' : '当前：深色 · 点击切换浅色'}>
      <button
        type="button"
        className="app-layout__header-collapse"
        aria-label={theme === 'light' ? '切换到深色主题' : '切换到浅色主题'}
        onClick={() => onChange(theme === 'light' ? 'dark' : 'light')}
      >
        <span className="app-layout__header-collapse-icon" aria-hidden="true">
          {theme === 'light' ? <MoonOutlined /> : <SunOutlined />}
        </span>
      </button>
    </Tooltip>
  );
}

/* ------------------------------------------------------------
 * CollapseToggle — header control (desktop only) to fold the
 * sidebar to icon-only mode.  Moved here from the sidebar's
 * bottom per Phase 3 spec.
 * ------------------------------------------------------------ */
interface CollapseToggleProps {
  collapsed: boolean;
  onChange: (next: boolean) => void;
}

function CollapseToggle({ collapsed, onChange }: CollapseToggleProps) {
  return (
    <Tooltip title={collapsed ? '展开侧边栏' : '折叠侧边栏'}>
      <button
        type="button"
        className="app-layout__header-collapse"
        aria-label={collapsed ? '展开侧边栏' : '折叠侧边栏'}
        aria-pressed={collapsed}
        onClick={() => onChange(!collapsed)}
      >
        <span className="app-layout__header-collapse-icon" aria-hidden="true">
          {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
        </span>
      </button>
    </Tooltip>
  );
}

/* ------------------------------------------------------------
 * ColorConventionToggle — header control for China (red-up /
 * green-down) vs US (green-up / red-down).  Phase 1 already
 * wires `<html data-color-convention>` for CSS variable
 * overrides; AppLayout writes the value to the DOM here.
 * ------------------------------------------------------------ */
function ColorConventionToggle() {
  const { colorConvention, setColorConvention } = useSettingsStore();
  return (
    <Segmented
      className="app-layout__header-segmented"
      size="small"
      value={colorConvention}
      onChange={(v) => setColorConvention(v as 'china' | 'us')}
      aria-label="切换涨跌色约定"
      options={[
        { label: '红涨绿跌', value: 'china' },
        { label: '绿涨红跌', value: 'us' },
      ]}
    />
  );
}

/* ============================================================
 * AppLayout — the app shell.
 * ============================================================ */
export default function AppLayout() {
  const { user, logout } = useAuthStore();
  const {
    colorConvention,
    mode,
    setMode,
    learningMode,
    setLearningMode,
  } = useSettingsStore();
  const [theme, setTheme] = useTheme();
  const [collapsed, setCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const location = useLocation();

  // First-login auto-trigger: pop the onboarding tour once per user.
  useEffect(() => {
    const userId = user?.id;
    if (!userId) return;
    try {
      const key = `ad:onboarding:${userId}:shown`;
      if (localStorage.getItem(key) === '1') return;
      localStorage.setItem(key, '1');
      window.dispatchEvent(new CustomEvent('ad-research:reopen-onboarding'));
    } catch {
      /* localStorage may be unavailable */
    }
  }, [user?.id]);

  // Phase 1: 同步 colorConvention 到 <html data-color-convention>,
  // 这样 theme.css 里的 CSS 变量切换才能生效。Phase 3 重写后保留。
  useEffect(() => {
    if (typeof document === 'undefined') return;
    document.documentElement.setAttribute('data-color-convention', colorConvention);
  }, [colorConvention]);

  // One-shot "已开启学习模式" hint so users notice the new default without
  // having to dig into the avatar menu.
  useEffect(() => {
    const userId = user?.id;
    if (!userId) return;
    if (!learningMode) return;
    try {
      const key = `ad:learning-mode:intro-shown:${userId}`;
      if (localStorage.getItem(key) === '1') return;
      localStorage.setItem(key, '1');
      message.info('已开启学习模式 — 关键术语旁会显示解释', 4);
    } catch {
      /* localStorage may be unavailable */
    }
  }, [user?.id, learningMode]);

  // Build a 1- or 2-segment breadcrumb from the route config + current URL.
  const breadcrumb = useMemo(() => {
    const path = location.pathname;
    if (path === '/' || path === '/dashboard') return null;

    const segments = path.split('/').filter(Boolean);
    let matchedPath = '';
    let matchedRoute: typeof menuRoutes[number] | undefined;
    for (const seg of segments) {
      const candidate = `/${segments.slice(0, segments.indexOf(seg) + 1).join('/')}`;
      const found = menuRoutes.find((r) => r.path === candidate);
      if (found) {
        matchedPath = candidate;
        matchedRoute = found;
      }
    }
    if (!matchedRoute || !matchedRoute.menu) return null;

    const tail = path.slice(matchedPath.length).replace(/^\/+/, '');
    const items: { label: string; path?: string }[] = [
      { label: '首页', path: '/dashboard' },
    ];
    if (matchedPath !== '/dashboard') {
      items.push({ label: matchedRoute.menu.name, path: matchedPath });
    }
    if (tail) {
      items.push({ label: tail });
    }
    return items;
  }, [location.pathname]);

  return (
    <div className="app-layout">
      {/* Mobile Drawer (left edge, same nav as desktop sidebar) */}
      {isMobile && (
        <Drawer
          placement="left"
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          width={260}
          closable={false}
        >
          <div className="app-layout__mobile-drawer">
            <SidebarContent collapsed={false} onItemClick={() => setDrawerOpen(false)} />
          </div>
        </Drawer>
      )}

      {/* Desktop Sidebar (fixed, collapsible) */}
      {!isMobile && (
        <aside
          className={`app-layout__sidebar ${collapsed ? 'app-layout__sidebar--collapsed' : ''}`}
        >
          <SidebarContent collapsed={collapsed} />
        </aside>
      )}

      {/* Main Content */}
      <main className={`app-layout__main ${isMobile ? 'app-layout__main--mobile' : ''}`}>
        {/* Header — sticky, 60px, var(--bg-base), hairline border */}
        <header className="app-layout__header">
          <div className="app-layout__header-left">
            {isMobile && (
              <div
                role="button"
                tabIndex={0}
                aria-label="打开导航菜单"
                onClick={() => setDrawerOpen(true)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setDrawerOpen(true);
                  }
                }}
                className="app-layout__icon-btn"
              >
                <MenuOutlined className="app-layout__menu-icon" aria-hidden="true" />
              </div>
            )}
            {breadcrumb && breadcrumb.length > 0 && (
              <nav aria-label="页面路径" className="app-layout__breadcrumb">
                {breadcrumb.map((item, idx) => {
                  const isLast = idx === breadcrumb.length - 1;
                  return (
                    <React.Fragment key={`${idx}-${item.label}`}>
                      {idx === 0 ? (
                        <HomeOutlined aria-hidden="true" className="app-layout__breadcrumb-home" />
                      ) : null}
                      {item.path && !isLast ? (
                        <span
                          role="link"
                          tabIndex={0}
                          onClick={() => navigate(item.path!)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              navigate(item.path!);
                            }
                          }}
                          className="app-layout__breadcrumb-link"
                        >
                          {item.label}
                        </span>
                      ) : (
                        <span
                          className="app-layout__breadcrumb-current"
                          aria-current={isLast ? 'page' : undefined}
                        >
                          {item.label}
                        </span>
                      )}
                      {!isLast && (
                        <RightOutlined
                          aria-hidden="true"
                          className="app-layout__breadcrumb-chevron"
                        />
                      )}
                    </React.Fragment>
                  );
                })}
              </nav>
            )}
          </div>

          {/* Header right cluster — collapse (desktop only), theme, color, density, user */}
          <div className="app-layout__header-controls">
            {!isMobile && (
              <>
                <CollapseToggle collapsed={collapsed} onChange={setCollapsed} />
                <ColorConventionToggle />
                <DensityToggle />
                <ThemeToggle theme={theme} onChange={setTheme} />
              </>
            )}

            {isMobile && (
              <Dropdown
                placement="bottomRight"
                trigger={['click']}
                menu={{
                  items: [
                    {
                      key: 'color-convention',
                      label: (
                        <div onClick={(e) => e.stopPropagation()}>
                          <ColorConventionToggle />
                        </div>
                      ),
                    },
                    {
                      key: 'theme',
                      label: (
                        <div onClick={(e) => e.stopPropagation()}>
                          <ThemeToggle theme={theme} onChange={setTheme} />
                        </div>
                      ),
                    },
                    {
                      key: 'density',
                      label: (
                        <div onClick={(e) => e.stopPropagation()}>
                          <DensityToggle />
                        </div>
                      ),
                    },
                  ],
                }}
              >
                <div
                  role="button"
                  tabIndex={0}
                  aria-label="显示设置"
                  className="app-layout__icon-btn"
                  onClick={(e) => e.stopPropagation()}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                    }
                  }}
                >
                  <SettingOutlined />
                </div>
              </Dropdown>
            )}

            <Dropdown
              menu={{
                items: [
                  {
                    key: 'mode',
                    label: (
                      <div
                        onClick={(e) => e.stopPropagation()}
                        className="app-layout__user-menu-mode"
                      >
                        <div className="app-layout__user-menu-label">教学模式</div>
                        <Segmented
                          value={mode}
                          onChange={(v) => setMode(v as 'novice' | 'pro')}
                          size="small"
                          options={[
                            { label: '新手', value: 'novice' },
                            { label: '专业', value: 'pro' },
                          ]}
                        />
                      </div>
                    ),
                  },
                  {
                    key: 'learning-mode',
                    label: (
                      <div
                        onClick={(e) => e.stopPropagation()}
                        className="app-layout__user-menu-mode"
                      >
                        <div className="app-layout__user-menu-label">
                          <BulbOutlined /> 学习模式
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <Switch
                            size="small"
                            checked={learningMode}
                            onChange={(v) => setLearningMode(v)}
                          />
                          <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                            开启后每个数字旁解释含义
                          </span>
                        </div>
                      </div>
                    ),
                  },
                  {
                    key: 'reopen-onboarding',
                    icon: <BookOutlined />,
                    label: '重新触发新手引导',
                    onClick: () => {
                      window.dispatchEvent(
                        new CustomEvent('ad-research:reopen-onboarding')
                      );
                    },
                  },
                  { type: 'divider' },
                  {
                    key: 'logout',
                    icon: <LogoutOutlined />,
                    label: '退出登录',
                    onClick: logout,
                  },
                ],
              }}
            >
              <div className="app-layout__user">
                <div className="app-layout__avatar" aria-hidden="true">
                  {(user?.username || 'U')[0].toUpperCase()}
                </div>
                {!isMobile && (
                  <span className="app-layout__username">{user?.username || '用户'}</span>
                )}
              </div>
            </Dropdown>
          </div>
        </header>

        {/* Page Content — padding per Phase 3 spec (32px desktop, 16px mobile) */}
        <div className="app-layout__content">
          <div className="app-layout__content-wrap">
            <Outlet />
            <footer className="app-layout__footer">
              数据来源：Tushare / FRED / 新浪财经 · 数据每日凌晨更新 · 本平台所有内容仅供参考，不构成投资建议 · © 2026 AD-Research
            </footer>
          </div>
        </div>
      </main>

      {/* K14: global onboarding tour, mounts only when not completed. */}
      <OnboardingTour />
    </div>
  );
}