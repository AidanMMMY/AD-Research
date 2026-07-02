import React, { useState, useMemo } from 'react';
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
  BankOutlined,
  FundOutlined,
  FireOutlined,
  FilePdfOutlined,
  BlockOutlined,
  SunOutlined,
  MoonOutlined,
} from '@ant-design/icons';
import { useAuthStore } from '@/stores/auth';
import { useSettingsStore } from '@/stores/settings';
import { menuRoutes } from '@/routes';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { useTheme, type Theme } from '@/hooks/useTheme';
import DensityToggle from '@/components/DensityToggle';

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
};

interface SidebarContentProps {
  collapsed: boolean;
  onItemClick?: () => void;
}

function SidebarContent({ collapsed, onItemClick }: SidebarContentProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuthStore();

  return (
    <>
      {/* Logo */}
      <div className="app-layout__logo">
        <div className="app-layout__logo-mark">E</div>
        {!collapsed && <span className="app-layout__logo-text">投研平台</span>}
      </div>

      {/* Menu Items */}
      <nav className="app-layout__nav">
        {menuRoutes.map((route) => {
          if (route.path.startsWith('/admin/') && user?.role !== 'admin') {
            return null;
          }

          const isActive = location.pathname === route.path;
          const Icon = route.menu?.icon ? iconMap[route.menu.icon] : null;
          const showDivider = route.menu?.dividerBefore;

          return (
            <React.Fragment key={route.path}>
              {showDivider && <div className="app-layout__nav-divider" />}
              <div
                onClick={() => {
                  navigate(route.path);
                  onItemClick?.();
                }}
                className={`app-layout__nav-item ${isActive ? 'app-layout__nav-item--active' : ''}`}
              >
                {Icon && (
                  <span className="app-layout__nav-icon">
                    <Icon />
                  </span>
                )}
                {!collapsed && <span className="app-layout__nav-label">{route.menu?.name}</span>}
              </div>
            </React.Fragment>
          );
        })}
      </nav>
    </>
  );
}

export default function AppLayout() {
  const { user, logout } = useAuthStore();
  const { colorConvention, setColorConvention } = useSettingsStore();
  const [theme, setTheme] = useTheme();
  const [collapsed, setCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const location = useLocation();

  // Build a 1- or 2-segment breadcrumb from the route config + current URL.
  // e.g. /instruments/510300.SH -> [首页, 标的列表, 510300.SH]
  const breadcrumb = useMemo(() => {
    const path = location.pathname;
    if (path === '/' || path === '/dashboard') return null;

    // Find the deepest menu route whose path is a prefix of the current
    // path and either an exact match or followed by a "/" + param segment.
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
      // Last segment is the detail id/code; show as-is (already user-readable
      // in most pages, and short enough not to need ellipsizing).
      items.push({ label: tail });
    }
    return items;
  }, [location.pathname]);

  return (
    <div className="app-layout">
      {/* Mobile Drawer */}
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

      {/* Desktop Sidebar */}
      {!isMobile && (
        <aside
          className={`app-layout__sidebar ${collapsed ? 'app-layout__sidebar--collapsed' : ''}`}
        >
          <SidebarContent collapsed={collapsed} />

          {/* Collapse Toggle */}
          <div className="app-layout__collapse-bar">
            <div
              role="button"
              tabIndex={0}
              aria-label={collapsed ? '展开侧边栏' : '折叠侧边栏'}
              onClick={() => setCollapsed(!collapsed)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  setCollapsed(!collapsed);
                }
              }}
              className="app-layout__icon-btn"
            >
              {collapsed ? <MenuUnfoldOutlined aria-hidden="true" /> : <MenuFoldOutlined aria-hidden="true" />}
            </div>
          </div>
        </aside>
      )}

      {/* Main Content */}
      <main className={`app-layout__main ${isMobile ? 'app-layout__main--mobile' : ''}`}>
        {/* Header */}
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
            {/* Breadcrumb */}
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

          <div className="app-layout__header-controls">
            {/* Color convention toggle */}
            <Segmented
              value={colorConvention}
              onChange={(v) => setColorConvention(v as 'china' | 'us')}
              aria-label="切换涨跌色约定"
              options={[
                { label: '红涨绿跌', value: 'china' },
                { label: '绿涨红跌', value: 'us' },
              ]}
            />

            {/* Theme toggle (clean / dark) */}
            <Segmented
              value={theme}
              onChange={(v) => setTheme(v as Theme)}
              aria-label="切换主题"
              options={[
                {
                  label: (
                    <Tooltip title="浅色主题">
                      <SunOutlined aria-label="浅色主题" />
                    </Tooltip>
                  ),
                  value: 'clean',
                },
                {
                  label: (
                    <Tooltip title="深色主题">
                      <MoonOutlined aria-label="深色主题" />
                    </Tooltip>
                  ),
                  value: 'dark',
                },
              ]}
              size="small"
            />

            {/* Density toggle (S1) */}
            <DensityToggle />

            <Dropdown
              menu={{
                items: [
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
                <div className="app-layout__avatar">
                  {(user?.username || 'U')[0].toUpperCase()}
                </div>
                {!isMobile && <span className="app-layout__username">{user?.username || '用户'}</span>}
              </div>
            </Dropdown>
          </div>
        </header>

        {/* Page Content */}
        <div className="app-layout__content">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
