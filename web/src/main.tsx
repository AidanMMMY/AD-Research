import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import App from './App';
import { getInitialTheme, type Theme } from '@/hooks/useTheme';
import './styles/theme.css';
import './styles/global.css';

// Apply persisted theme synchronously to avoid flash of wrong theme
const initialTheme = getInitialTheme();
document.documentElement.setAttribute('data-theme', initialTheme);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
});

/**
 * Build the Ant Design theme object for the active visual mode.
 *
 * Two visual modes:
 *   - 'clean' (default) — light, clean surface with blue accent
 *   - 'dark'            — existing terminal dark + green accent
 *
 * The CSS variable layer (theme.css) re-skins the entire app via
 * <html data-theme="clean"> or <html data-theme="dark">, but Ant Design's
 * component tokens (colorPrimary, borderRadius, …) are JS-side and don't read
 * CSS variables. So we mirror the palette here in JS.
 *
 * Re-runs when `<html data-theme>` changes via the `themechange`
 * custom event dispatched from useTheme().
 */
const useAntdTheme = () => {
  const [mode, setMode] = useState<Theme>(() =>
    typeof document !== 'undefined'
      ? (document.documentElement.getAttribute('data-theme') as Theme) || 'clean'
      : 'clean',
  );

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<Theme>).detail;
      setMode(detail === 'dark' ? 'dark' : 'clean');
    };
    document.addEventListener('themechange', handler);
    return () => document.removeEventListener('themechange', handler);
  }, []);

  if (mode === 'dark') {
    // Dark terminal theme
    return {
      algorithm: theme.darkAlgorithm,
      token: {
        colorPrimary: '#5fa87a',
        colorInfo: '#5fa87a',
        colorSuccess: '#5fa87a',
        colorWarning: '#eab308',
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
          activeBorderColor: '#5fa87a',
          activeShadow: '0 0 0 2px rgba(95,168,122,0.10)',
        },
        Select: {
          borderRadius: 8,
          colorBgContainer: 'rgba(255,255,255,0.02)',
          optionSelectedBg: 'rgba(95,168,122,0.10)',
          optionSelectedColor: '#5fa87a',
        },
        Tabs: {
          inkBarColor: '#5fa87a',
          itemSelectedColor: '#5fa87a',
          itemHoverColor: '#f5f5f0',
          itemColor: '#444444',
        },
      },
    };
  }

  // Clean (default) — light surface with blue accent
  return {
    algorithm: theme.defaultAlgorithm,
    token: {
      colorPrimary: '#2e5bff',
      colorInfo: '#2e5bff',
      colorSuccess: '#10b981',
      colorWarning: '#f59e0b',
      colorError: '#ef4444',
      colorBgBase: '#ffffff',
      colorBgContainer: '#ffffff',
      colorBgElevated: '#f7f7f8',
      colorTextBase: '#111113',
      colorTextSecondary: '#6b7280',
      colorTextTertiary: '#9ca3af',
      colorBorder: '#e5e7eb',
      colorBorderSecondary: '#f4f4f5',
      borderRadius: 8,
      borderRadiusSM: 4,
      borderRadiusLG: 12,
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
        headerColor: '#9ca3af',
        headerSplitColor: 'transparent',
        rowHoverBg: 'rgba(0,0,0,0.03)',
        borderColor: '#e5e7eb',
        cellPaddingInline: 16,
        cellPaddingBlock: 14,
        headerBorderRadius: 0,
      },
      Button: {
        borderRadius: 8,
        borderRadiusSM: 4,
        primaryShadow: 'none',
        colorPrimary: '#2e5bff',
        colorPrimaryHover: '#1a4bff',
        colorPrimaryActive: '#153de6',
        colorTextLightSolid: '#ffffff',
      },
      Card: {
        borderRadius: 12,
        borderRadiusLG: 12,
        colorBgContainer: '#ffffff',
      },
      Modal: {
        borderRadiusLG: 12,
        colorBgElevated: '#f7f7f8',
      },
      Drawer: {
        colorBgElevated: '#f7f7f8',
      },
      Tag: {
        borderRadiusSM: 4,
        defaultBg: '#f4f4f5',
        defaultColor: '#6b7280',
        colorTextLightSolid: '#ffffff',
      },
      Input: {
        borderRadius: 8,
        colorBgContainer: '#ffffff',
        activeBorderColor: '#2e5bff',
        activeShadow: '0 0 0 2px rgba(46,91,255,0.08)',
      },
      Select: {
        borderRadius: 8,
        colorBgContainer: '#ffffff',
        optionSelectedBg: 'rgba(46,91,255,0.08)',
        optionSelectedColor: '#2e5bff',
      },
      Tabs: {
        inkBarColor: '#2e5bff',
        itemSelectedColor: '#111113',
        itemHoverColor: '#6b7280',
        itemColor: '#9ca3af',
      },
      Alert: {
        colorError: '#ef4444',
        colorErrorBg: '#fef2f2',
        colorErrorBorder: '#fecaca',
        colorWarning: '#f59e0b',
        colorWarningBg: '#fffbeb',
        colorWarningBorder: '#fde68a',
        colorSuccess: '#10b981',
        colorSuccessBg: '#ecfdf5',
        colorSuccessBorder: '#a7f3d0',
        colorInfo: '#2e5bff',
        colorInfoBg: '#eff4ff',
        colorInfoBorder: '#c7d7ff',
      },
      Tooltip: {
        colorTextLightSolid: '#ffffff',
      },
      Notification: {
        colorTextLightSolid: '#ffffff',
      },
    },
  };
};

function ThemedApp() {
  const antdTheme = useAntdTheme();
  return (
    <ConfigProvider locale={zhCN} theme={antdTheme}>
      <App />
    </ConfigProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemedApp />
    </QueryClientProvider>
  </React.StrictMode>,
);
