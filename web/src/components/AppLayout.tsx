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
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MenuOutlined,
  MonitorOutlined,
  HomeOutlined,
  RightOutlined,
} from '@ant-design/icons';
import { useAuthStore } from '@/stores/auth';
import { useSettingsStore } from '@/stores/settings';
import { menuRoutes } from '@/routes';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { useTheme } from '@/hooks/useTheme';
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
};

const SIDEBAR_WIDTH = 220;
const SIDEBAR_COLLAPSED = 72;

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
      <div
        style={{
          height: 64,
          display: 'flex',
          alignItems: 'center',
          padding: collapsed ? '0 20px' : '0 24px',
          borderBottom: '1px solid var(--border-default)',
          gap: 12,
        }}
      >
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: 'var(--radius-lg)',
            background: 'var(--accent)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 16,
            fontWeight: 700,
            color: 'var(--text-on-accent)',
            flexShrink: 0,
          }}
        >
          E
        </div>
        {!collapsed && (
          <span
            style={{
              fontSize: 'var(--text-body-size)',
              fontWeight: 500,
              color: 'var(--text-primary)',
              letterSpacing: '0.02em',
              whiteSpace: 'nowrap',
            }}
          >
            投研平台
          </span>
        )}
      </div>

      {/* Menu Items */}
      <nav style={{ flex: 1, padding: '12px 8px', overflowY: 'auto' }}>
        {menuRoutes.map((route) => {
          if (route.path.startsWith('/admin/') && user?.role !== 'admin') {
            return null;
          }

          const isActive = location.pathname === route.path;
          const Icon = route.menu?.icon ? iconMap[route.menu.icon] : null;
          const showDivider = route.menu?.dividerBefore;

          return (
            <React.Fragment key={route.path}>
              {showDivider && (
                <div
                  style={{
                    margin: '8px 12px',
                    borderTop: '1px solid var(--border-default)',
                  }}
                />
              )}
              <div
              onClick={() => {
                navigate(route.path);
                onItemClick?.();
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: collapsed ? '10px 0' : '10px 14px',
                marginBottom: 2,
                borderRadius: 'var(--radius-lg)',
                cursor: 'pointer',
                transition: 'background var(--transition-fast), color var(--transition-fast)',
                justifyContent: collapsed ? 'center' : 'flex-start',
                color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                background: isActive ? 'var(--bg-active)' : 'transparent',
              }}
              onMouseEnter={(e) => {
                if (!isActive) {
                  e.currentTarget.style.background = 'var(--bg-hover)';
                  e.currentTarget.style.color = 'var(--text-primary)';
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive) {
                  e.currentTarget.style.background = 'transparent';
                  e.currentTarget.style.color = 'var(--text-secondary)';
                }
              }}
            >
              {Icon && (
                <span
                  style={{
                    fontSize: 18,
                    flexShrink: 0,
                    opacity: isActive ? 1 : 0.7,
                    display: 'inline-flex',
                    alignItems: 'center',
                  }}
                >
                  <Icon />
                </span>
              )}
              {!collapsed && (
                <span
                  style={{
                    fontSize: 14,
                    fontWeight: isActive ? 500 : 400,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {route.menu?.name}
                </span>
              )}
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

  const sidebarWidth = isMobile ? 0 : collapsed ? SIDEBAR_COLLAPSED : SIDEBAR_WIDTH;

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
    <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg-base)' }}>
      {/* Mobile Drawer */}
      {isMobile && (
        <Drawer
          placement="left"
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          width={260}
          closable={false}
          styles={{
            body: { padding: 0, background: 'var(--bg-elevated)' },
            header: { display: 'none' },
            mask: { background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' },
          }}
        >
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              height: '100%',
            }}
          >
            <SidebarContent collapsed={false} onItemClick={() => setDrawerOpen(false)} />
          </div>
        </Drawer>
      )}

      {/* Desktop Sidebar */}
      {!isMobile && (
        <aside
          style={{
            width: sidebarWidth,
            flexShrink: 0,
            background: 'var(--bg-elevated)',
            borderRight: '1px solid var(--border-default)',
            display: 'flex',
            flexDirection: 'column',
            position: 'fixed',
            top: 0,
            left: 0,
            bottom: 0,
            zIndex: 100,
            transition: 'width 300ms cubic-bezier(0.4, 0, 0.2, 1)',
            overflow: 'hidden',
          }}
        >
          <SidebarContent collapsed={collapsed} />

          {/* Collapse Toggle */}
          <div
            style={{
              padding: '12px 16px',
              borderTop: '1px solid var(--border-default)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: collapsed ? 'center' : 'flex-end',
            }}
          >
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
              style={{
                width: 32,
                height: 32,
                borderRadius: 8,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                color: 'var(--text-secondary)',
                transition: 'background 200ms ease, color 200ms ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'var(--bg-active)';
                e.currentTarget.style.color = 'var(--text-primary)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent';
                e.currentTarget.style.color = 'var(--text-secondary)';
              }}
            >
              {collapsed ? <MenuUnfoldOutlined aria-hidden="true" /> : <MenuFoldOutlined aria-hidden="true" />}
            </div>
          </div>
        </aside>
      )}

      {/* Main Content */}
      <main
        style={{
          flex: 1,
          marginLeft: sidebarWidth,
          transition: 'margin-left 300ms cubic-bezier(0.4, 0, 0.2, 1)',
          display: 'flex',
          flexDirection: 'column',
          minWidth: 0,
        }}
      >
        {/* Header */}
        <header
          style={{
            height: 64,
            background: 'rgba(10, 10, 10, 0.85)', /* var(--bg-base) at 85% opacity for frosted glass */
            backdropFilter: 'blur(12px)',
            borderBottom: '1px solid var(--border-default)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: isMobile ? '0 16px' : '0 32px',
            position: 'sticky',
            top: 0,
            zIndex: 50,
            gap: 12,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0, flex: '1 1 auto' }}>
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
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: 10,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                  color: 'var(--text-secondary)',
                  transition: 'background 200ms ease, color 200ms ease',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'var(--bg-active)';
                  e.currentTarget.style.color = 'var(--text-primary)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'transparent';
                  e.currentTarget.style.color = 'var(--text-secondary)';
                }}
              >
                <MenuOutlined style={{ fontSize: 18 }} aria-hidden="true" />
              </div>
            )}
            {/* Breadcrumb */}
            {breadcrumb && breadcrumb.length > 0 && (
              <nav
                aria-label="页面路径"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  minWidth: 0,
                  flex: '1 1 auto',
                  fontSize: 'var(--text-small-size)',
                  color: 'var(--text-tertiary)',
                  letterSpacing: '0.04em',
                  overflow: 'hidden',
                  whiteSpace: 'nowrap',
                  textOverflow: 'ellipsis',
                }}
              >
                {breadcrumb.map((item, idx) => {
                  const isLast = idx === breadcrumb.length - 1;
                  return (
                    <React.Fragment key={`${idx}-${item.label}`}>
                      {idx === 0 ? (
                        <HomeOutlined aria-hidden="true" style={{ fontSize: 12, opacity: 0.7 }} />
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
                          style={{
                            cursor: 'pointer',
                            color: 'var(--text-tertiary)',
                            transition: 'color var(--transition-fast)',
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.color = 'var(--text-primary)';
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.color = 'var(--text-tertiary)';
                          }}
                        >
                          {item.label}
                        </span>
                      ) : (
                        <span
                          style={{
                            color: 'var(--text-primary)',
                            fontWeight: 500,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                          }}
                          aria-current={isLast ? 'page' : undefined}
                        >
                          {item.label}
                        </span>
                      )}
                      {!isLast && (
                        <RightOutlined
                          aria-hidden="true"
                          style={{ fontSize: 9, opacity: 0.4 }}
                        />
                      )}
                    </React.Fragment>
                  );
                })}
              </nav>
            )}
          </div>

          {/* Color convention toggle */}
          <Segmented
            value={colorConvention}
            onChange={(v) => setColorConvention(v as 'china' | 'us')}
            aria-label="切换涨跌色约定"
            options={[
              { label: '红涨绿跌', value: 'china' },
              { label: '绿涨红跌', value: 'us' },
            ]}
            style={{ background: 'var(--bg-hover)', borderRadius: 10 }}
          />

          {/* Theme toggle (terminal / print) */}
          <Segmented
            value={theme}
            onChange={(v) => setTheme(v as 'terminal' | 'print')}
            aria-label="切换主题"
            options={[
              {
                label: (
                  <Tooltip title="终端主题（深色 / 绿）">
                    <MonitorOutlined aria-label="终端主题" />
                  </Tooltip>
                ),
                value: 'terminal',
              },
              {
                label: (
                  <Tooltip title="印刷主题（暖米 / 衬线）">
                    <ReadOutlined aria-label="印刷主题" />
                  </Tooltip>
                ),
                value: 'print',
              },
            ]}
            size="small"
            style={{ background: 'var(--bg-hover)', borderRadius: 10 }}
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
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--space-3)',
                cursor: 'pointer',
                padding: '6px 12px',
                borderRadius: 10,
                transition: 'background 200ms',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'var(--bg-hover)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent';
              }}
            >
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: '50%',
                  background: 'var(--bg-input)',
                  border: '1px solid var(--border-default)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 14,
                  fontWeight: 600,
                  color: 'var(--text-primary)',
                }}
              >
                {(user?.username || 'U')[0].toUpperCase()}
              </div>
              {!isMobile && (
                <span style={{ color: 'var(--text-primary)', fontSize: 14, fontWeight: 500 }}>
                  {user?.username || '用户'}
                </span>
              )}
            </div>
          </Dropdown>
        </header>

        {/* Page Content */}
        <div
          style={{
            flex: 1,
            padding: isMobile ? '16px' : '28px 32px',
            overflow: 'auto',
          }}
        >
          <Outlet />
        </div>
      </main>
    </div>
  );
}
