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
    colorPrimary: '#818cf8',
    colorInfo: '#06b6d4',
    colorSuccess: '#22c55e',
    colorWarning: '#eab308',
    colorError: '#ef4444',
    colorBgBase: '#070b14',
    colorBgContainer: 'rgba(255,255,255,0.03)',
    colorBgElevated: '#0f1729',
    colorTextBase: '#f1f5f9',
    colorBorder: 'rgba(255,255,255,0.06)',
    borderRadius: 12,
    borderRadiusSM: 8,
    borderRadiusLG: 16,
    fontFamily: "-apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif",
    controlHeight: 36,
    controlHeightSM: 30,
    controlHeightLG: 44,
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
