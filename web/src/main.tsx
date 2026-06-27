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

// Hybrid 暗色主题配置 (Swiss skeleton + Bento warmth)
const antdTheme = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: '#d4a373',
    colorInfo: '#d4a373',
    colorSuccess: '#5fa87a',
    colorWarning: '#d4a373',
    colorError: '#c96b6b',
    colorBgBase: '#0a0a0a',
    colorBgContainer: '#111111',
    colorBgElevated: '#111111',
    colorTextBase: '#f5f5f0',
    colorTextSecondary: '#888888',
    colorTextTertiary: '#444444',
    colorBorder: 'rgba(255,255,255,0.06)',
    colorBorderSecondary: 'rgba(255,255,255,0.04)',
    borderRadius: 8,
    borderRadiusSM: 6,
    borderRadiusLG: 12,
    borderRadiusXS: 4,
    fontFamily: "Inter, 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif",
    fontFamilyCode: "'JetBrains Mono', 'SF Mono', 'Fira Code', 'Cascadia Code', monospace",
    controlHeight: 36,
    controlHeightSM: 30,
    controlHeightLG: 44,
  },
  components: {
    Table: {
      headerBg: 'transparent',
      headerColor: '#444444',
      headerSplitColor: 'transparent',
      rowHoverBg: 'rgba(255,255,255,0.03)',
      borderColor: 'rgba(255,255,255,0.06)',
      cellPaddingInline: 16,
      cellPaddingBlock: 14,
      headerBorderRadius: 0,
    },
    Button: {
      borderRadius: 8,
      borderRadiusSM: 6,
      primaryShadow: 'none',
    },
    Card: {
      borderRadius: 14,
      borderRadiusLG: 16,
      colorBgContainer: '#111111',
    },
    Modal: {
      borderRadiusLG: 16,
      colorBgElevated: '#111111',
    },
    Drawer: {
      colorBgElevated: '#111111',
    },
    Tag: {
      borderRadiusSM: 5,
      defaultBg: 'rgba(255,255,255,0.04)',
      defaultColor: '#888888',
    },
    Input: {
      borderRadius: 8,
      colorBgContainer: 'rgba(255,255,255,0.02)',
      activeBorderColor: '#d4a373',
      activeShadow: '0 0 0 2px rgba(212,163,115,0.10)',
    },
    Select: {
      borderRadius: 8,
      colorBgContainer: 'rgba(255,255,255,0.02)',
      optionSelectedBg: 'rgba(212,163,115,0.10)',
      optionSelectedColor: '#d4a373',
    },
    Tabs: {
      inkBarColor: '#d4a373',
      itemSelectedColor: '#d4a373',
      itemHoverColor: '#f5f5f0',
      itemColor: '#444444',
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
