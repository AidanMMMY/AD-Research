import React from 'react';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { ProLayout } from '@ant-design/pro-components';
import { Dropdown } from 'antd';
import {
  LogoutOutlined,
  DashboardOutlined,
  OrderedListOutlined,
  FilterOutlined,
  AppstoreOutlined,
  TrophyOutlined,
  FileTextOutlined,
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
};

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuthStore();

  const menuItems = menuRoutes.map((route) => ({
    path: route.path,
    name: route.menu?.name,
    icon: route.menu?.icon ? React.createElement(iconMap[route.menu.icon]) : null,
  }));

  return (
    <ProLayout
      title="ETF投研平台"
      logo={null}
      layout="side"
      navTheme="realDark"
      fixSiderbar
      fixedHeader
      route={{ path: '/', routes: menuItems }}
      location={{ pathname: location.pathname }}
      menuItemRender={(item, dom) => (
        <a onClick={() => navigate(item.path || '/dashboard')}>{dom}</a>
      )}
      avatarProps={{
        src: null,
        size: 'small',
        title: user?.username || '用户',
        render: (_, dom) => (
          <Dropdown
            menu={{
              items: [
                { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: logout },
              ],
            }}
          >
            {dom}
          </Dropdown>
        ),
      }}
    >
      <Outlet />
    </ProLayout>
  );
}
