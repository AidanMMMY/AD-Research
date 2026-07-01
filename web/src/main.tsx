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
if (initialTheme === 'print') {
  document.documentElement.setAttribute('data-theme', 'print');
} else {
  document.documentElement.removeAttribute('data-theme');
}

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
 * Two coexisting visual modes:
 *   - 'terminal' (default) — Swiss dark + Bento warmth, terminal green accent
 *   - 'print'             — FT/WSJ cream paper, brick-red accent, sharp corners
 *
 * The CSS variable layer (theme.css) re-skins the entire app via
 * <html data-theme="print">, but Ant Design's component tokens
 * (colorPrimary, borderRadius, …) are JS-side and don't read CSS
 * variables. So we mirror the palette here in JS.
 *
 * Re-runs when `<html data-theme>` changes via the `themechange`
 * custom event dispatched from useTheme().
 */
const useAntdTheme = () => {
  const [mode, setMode] = useState<Theme>(() =>
    typeof document !== 'undefined' &&
    document.documentElement.getAttribute('data-theme') === 'print'
      ? 'print'
      : 'terminal',
  );

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<Theme>).detail;
      setMode(detail === 'print' ? 'print' : 'terminal');
    };
    document.addEventListener('themechange', handler);
    return () => document.removeEventListener('themechange', handler);
  }, []);

  if (mode === 'print') {
    return {
      algorithm: theme.defaultAlgorithm,
      token: {
        colorPrimary: '#8b1a1a',
        colorInfo: '#8b1a1a',
        colorSuccess: '#166534',
        colorWarning: '#b45309',
        colorError: '#b91c1c',
        colorBgBase: '#f5f1e8',
        colorBgContainer: '#fbf7ec',
        colorBgElevated: '#fbf7ec',
        colorTextBase: '#1a1a1a',
        colorTextSecondary: '#555555',
        colorTextTertiary: '#7a7a7a',
        colorBorder: '#d4cebd',
        colorBorderSecondary: '#d4cebd',
        borderRadius: 0,
        borderRadiusSM: 0,
        borderRadiusLG: 0,
        borderRadiusXS: 0,
        fontFamily: "'Source Serif 4', Georgia, 'Times New Roman', serif",
        fontFamilyCode: "'JetBrains Mono', 'SF Mono', Menlo, monospace",
        controlHeight: 36,
        controlHeightSM: 30,
        controlHeightLG: 44,
      },
      components: {
        Table: {
          headerBg: 'transparent',
          headerColor: '#1a1a1a',
          headerSplitColor: 'transparent',
          rowHoverBg: 'rgba(15, 15, 15, 0.04)',
          borderColor: '#d4cebd',
          cellPaddingInline: 16,
          cellPaddingBlock: 14,
          headerBorderRadius: 0,
        },
        Button: {
          borderRadius: 0,
          borderRadiusSM: 0,
          primaryShadow: 'none',
        },
        Card: {
          borderRadius: 0,
          borderRadiusLG: 0,
          colorBgContainer: '#fbf7ec',
        },
        Modal: {
          borderRadiusLG: 0,
          colorBgElevated: '#fbf7ec',
        },
        Drawer: {
          colorBgElevated: '#fbf7ec',
        },
        Tag: {
          borderRadiusSM: 0,
          defaultBg: '#fffdf6',
          defaultColor: '#555555',
        },
        Input: {
          borderRadius: 0,
          colorBgContainer: '#fffdf6',
          activeBorderColor: '#8b1a1a',
          activeShadow: '0 0 0 2px rgba(139, 26, 26, 0.10)',
        },
        Select: {
          borderRadius: 0,
          colorBgContainer: '#fffdf6',
          optionSelectedBg: 'rgba(139, 26, 26, 0.10)',
          optionSelectedColor: '#8b1a1a',
        },
        Tabs: {
          inkBarColor: '#8b1a1a',
          itemSelectedColor: '#1a1a1a',
          itemHoverColor: '#1a1a1a',
          itemColor: '#7a7a7a',
        },
      },
    };
  }

  // Terminal (default) — Swiss skeleton + Bento warmth
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