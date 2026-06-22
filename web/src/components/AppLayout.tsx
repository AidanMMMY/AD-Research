import React, { useState } from 'react';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { Dropdown } from 'antd';
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
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons';
import { useAuthStore } from '@/stores/auth';
import { menuRoutes } from '@/routes';

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
};

const SIDEBAR_WIDTH = 220;
const SIDEBAR_COLLAPSED = 72;

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuthStore();
  const [collapsed, setCollapsed] = useState(false);

  const sidebarWidth = collapsed ? SIDEBAR_COLLAPSED : SIDEBAR_WIDTH;

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#070b14' }}>
      {/* Sidebar */}
      <aside
        style={{
          width: sidebarWidth,
          flexShrink: 0,
          background: 'linear-gradient(180deg, #0a0f1e 0%, #0d1326 100%)',
          borderRight: '1px solid rgba(255, 255, 255, 0.06)',
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
        {/* Logo */}
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            padding: collapsed ? '0 20px' : '0 24px',
            borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
            gap: 12,
          }}
        >
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 10,
              background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 18,
              fontWeight: 700,
              color: '#fff',
              flexShrink: 0,
              boxShadow: '0 0 16px rgba(99, 102, 241, 0.4)',
            }}
          >
            E
          </div>
          {!collapsed && (
            <span
              style={{
                fontSize: 16,
                fontWeight: 700,
                color: '#f1f5f9',
                letterSpacing: '1px',
                whiteSpace: 'nowrap',
              }}
            >
              ETF投研
            </span>
          )}
        </div>

        {/* Menu Items */}
        <nav style={{ flex: 1, padding: '16px 12px', overflowY: 'auto' }}>
          {menuRoutes.map((route) => {
            const isActive = location.pathname === route.path;
            const Icon = route.menu?.icon ? iconMap[route.menu.icon] : null;

            return (
              <div
                key={route.path}
                onClick={() => navigate(route.path)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  padding: collapsed ? '12px 0' : '12px 16px',
                  marginBottom: 4,
                  borderRadius: 12,
                  cursor: 'pointer',
                  transition: 'all 200ms ease',
                  justifyContent: collapsed ? 'center' : 'flex-start',
                  position: 'relative',
                  ...(isActive
                    ? {
                        background:
                          'linear-gradient(90deg, rgba(99,102,241,0.15) 0%, rgba(139,92,246,0.08) 100%)',
                        color: '#818cf8',
                      }
                    : {
                        color: '#94a3b8',
                      }),
                }}
                onMouseEnter={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
                    e.currentTarget.style.color = '#e2e8f0';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.background = 'transparent';
                    e.currentTarget.style.color = '#94a3b8';
                  }
                }}
              >
                {isActive && (
                  <div
                    style={{
                      position: 'absolute',
                      left: 0,
                      top: '50%',
                      transform: 'translateY(-50%)',
                      width: 3,
                      height: 20,
                      borderRadius: '0 3px 3px 0',
                      background: 'linear-gradient(180deg, #6366f1, #8b5cf6)',
                      boxShadow: '0 0 8px rgba(99, 102, 241, 0.5)',
                    }}
                  />
                )}
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
                      fontWeight: isActive ? 600 : 400,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {route.menu?.name}
                  </span>
                )}
              </div>
            );
          })}
        </nav>

        {/* Collapse Toggle */}
        <div
          style={{
            padding: '12px 16px',
            borderTop: '1px solid rgba(255, 255, 255, 0.06)',
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
              color: '#64748b',
              transition: 'all 200ms',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(255,255,255,0.06)';
              e.currentTarget.style.color = '#e2e8f0';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'transparent';
              e.currentTarget.style.color = '#64748b';
            }}
          >
            {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main
        style={{
          flex: 1,
          marginLeft: sidebarWidth,
          transition: 'margin-left 300ms cubic-bezier(0.4, 0, 0.2, 1)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Header */}
        <header
          style={{
            height: 64,
            background: 'rgba(7, 11, 20, 0.8)',
            backdropFilter: 'blur(12px)',
            borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 32px',
            position: 'sticky',
            top: 0,
            zIndex: 50,
          }}
        >
          <div>
            {/* Breadcrumb or page title could go here */}
          </div>

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
                  background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 14,
                  fontWeight: 600,
                  color: '#fff',
                }}
              >
                {(user?.username || 'U')[0].toUpperCase()}
              </div>
              <span style={{ color: '#e2e8f0', fontSize: 14, fontWeight: 500 }}>
                {user?.username || '用户'}
              </span>
            </div>
          </Dropdown>
        </header>

        {/* Page Content */}
        <div
          style={{
            flex: 1,
            padding: '28px 32px',
            overflow: 'auto',
          }}
        >
          <Outlet />
        </div>
      </main>
    </div>
  );
}
