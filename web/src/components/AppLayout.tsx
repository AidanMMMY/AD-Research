import React, { useState } from 'react';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { Dropdown, Drawer, Segmented } from 'antd';
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
  SmileOutlined,
  RobotOutlined,
  CloudServerOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MenuOutlined,
} from '@ant-design/icons';
import { useAuthStore } from '@/stores/auth';
import { useSettingsStore } from '@/stores/settings';
import { menuRoutes } from '@/routes';
import { useIsMobile } from '@/hooks/useBreakpoint';

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
  SmileOutlined,
  RobotOutlined,
  CloudServerOutlined,
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
            color: '#0a0a0a',
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
                transition: 'all var(--transition-fast)',
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
  const [collapsed, setCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const isMobile = useIsMobile();

  const sidebarWidth = isMobile ? 0 : collapsed ? SIDEBAR_COLLAPSED : SIDEBAR_WIDTH;

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
              onClick={() => setCollapsed(!collapsed)}
              style={{
                width: 32,
                height: 32,
                borderRadius: 8,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                color: 'var(--text-secondary)',
                transition: 'all 200ms',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(255,255,255,0.06)';
                e.currentTarget.style.color = 'var(--text-primary)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent';
                e.currentTarget.style.color = 'var(--text-secondary)';
              }}
            >
              {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
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
            background: 'rgba(10, 10, 10, 0.85)',
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
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {isMobile && (
              <div
                onClick={() => setDrawerOpen(true)}
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: 10,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                  color: 'var(--text-secondary)',
                  transition: 'all 200ms',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(255,255,255,0.06)';
                  e.currentTarget.style.color = 'var(--text-primary)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'transparent';
                  e.currentTarget.style.color = 'var(--text-secondary)';
                }}
              >
                <MenuOutlined style={{ fontSize: 18 }} />
              </div>
            )}
            {/* Breadcrumb or page title could go here */}
          </div>

          {/* Color convention toggle */}
          <Segmented
            value={colorConvention}
            onChange={(v) => setColorConvention(v as 'china' | 'us')}
            options={[
              { label: '红涨绿跌', value: 'china' },
              { label: '绿涨红跌', value: 'us' },
            ]}
            style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 10 }}
          />

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
                gap: 10,
                cursor: 'pointer',
                padding: '6px 12px',
                borderRadius: 10,
                transition: 'background 200ms',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
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
