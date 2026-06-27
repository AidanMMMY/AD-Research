import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import App from './App';
import './styles/theme.css';
import './styles/global.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
});

// 暗色主题配置
const antdTheme = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: '#22d3ee',
    colorInfo: '#22d3ee',
    colorSuccess: '#22c55e',
    colorWarning: '#eab308',
    colorError: '#ef4444',
    colorBgBase: '#0a0a0a',
    colorBgContainer: '#111111',
    colorBgElevated: '#111111',
    colorTextBase: '#f5f5f5',
    colorTextSecondary: '#aaaaaa',
    colorTextTertiary: '#555555',
    colorBorder: 'rgba(255,255,255,0.06)',
    colorBorderSecondary: 'rgba(255,255,255,0.04)',
    borderRadius: 4,
    borderRadiusSM: 3,
    borderRadiusLG: 8,
    borderRadiusXS: 2,
    fontFamily: "Inter, 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif",
    fontFamilyCode: "'JetBrains Mono', 'SF Mono', 'Fira Code', 'Cascadia Code', monospace",
    controlHeight: 36,
    controlHeightSM: 30,
    controlHeightLG: 44,
  },
  components: {
    Table: {
      headerBg: 'transparent',
      headerColor: '#555555',
      headerSplitColor: 'transparent',
      rowHoverBg: 'rgba(255,255,255,0.03)',
      borderColor: 'rgba(255,255,255,0.06)',
      cellPaddingInline: 16,
      cellPaddingBlock: 12,
      headerBorderRadius: 0,
    },
    Button: {
      borderRadius: 4,
      borderRadiusSM: 3,
      primaryShadow: 'none',
    },
    Card: {
      borderRadius: 8,
      borderRadiusLG: 12,
      colorBgContainer: '#111111',
    },
    Modal: {
      borderRadiusLG: 12,
      colorBgElevated: '#111111',
    },
    Drawer: {
      colorBgElevated: '#111111',
    },
    Tag: {
      borderRadiusSM: 3,
      defaultBg: 'rgba(255,255,255,0.02)',
      defaultColor: '#aaaaaa',
    },
    Input: {
      borderRadius: 4,
      colorBgContainer: 'rgba(255,255,255,0.02)',
      activeBorderColor: '#22d3ee',
      activeShadow: '0 0 0 2px rgba(34,211,238,0.08)',
    },
    Select: {
      borderRadius: 4,
      colorBgContainer: 'rgba(255,255,255,0.02)',
      optionSelectedBg: 'rgba(34,211,238,0.08)',
      optionSelectedColor: '#22d3ee',
    },
    Tabs: {
      inkBarColor: '#22d3ee',
      itemSelectedColor: '#22d3ee',
      itemHoverColor: '#f5f5f5',
      itemColor: '#555555',
    },
  },
};

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ConfigProvider locale={zhCN} theme={antdTheme}>
        <App />
      </ConfigProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
