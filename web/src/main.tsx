import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import App from './App';
import { getInitialTheme, type Theme } from '@/hooks/useTheme';
import { readCssVar } from '@/utils/cssVar';
// 自托管字体（Inter + JetBrains Mono），统一跨平台字体体验
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import '@fontsource/inter/700.css';
import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/jetbrains-mono/500.css';
import './styles/theme.css';
import './styles/global.css';

// Apply persisted theme synchronously to avoid flash of wrong theme
const initialTheme = getInitialTheme();
document.documentElement.setAttribute('data-theme', initialTheme);
// Default color convention attribute is applied by AppLayout after mount
// (settings store value is the source of truth; SSR/no-store fallback is
// "china" via the :root CSS rules above).

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
});

/**
 * Build antd v5 theme tokens from the v2 design system defined in theme.css.
 * All seed colors are read from CSS custom properties so antd components stay
 * in sync with the data-theme / data-accent attributes on <html>.
 * The data-color-convention attribute is untouched because it only affects
 * market rise/fall colors, which are not used by antd's base palette.
 */
const useAntdTheme = () => {
  const [mode, setMode] = useState<Theme>(() =>
    typeof document !== 'undefined'
      ? (document.documentElement.getAttribute('data-theme') as Theme) || 'light'
      : 'light',
  );

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<Theme>).detail;
      setMode(detail === 'dark' ? 'dark' : 'light');
    };
    document.addEventListener('themechange', handler);
    return () => document.removeEventListener('themechange', handler);
  }, []);

  const css = (name: string, fallback: string) => readCssVar(name, fallback);
  const isDark = mode === 'dark';

  return {
    algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      colorPrimary: css('--accent', '#2563EB'),
      colorPrimaryHover: css('--accent-hover', '#1D4ED8'),
      colorPrimaryActive: css('--accent-active', '#1E40AF'),
      colorInfo: css('--color-info', '#2563EB'),
      colorSuccess: css('--color-success', '#30A46C'),
      colorWarning: css('--color-warning', '#F0B100'),
      colorError: css('--color-error', '#E5484D'),
      colorBgBase: css('--bg-base', '#FAFBFC'),
      colorBgContainer: css('--card-bg', '#ffffff'),
      colorBgElevated: css('--bg-elevated', '#F3F5F7'),
      colorTextBase: css('--text-primary', '#0F1115'),
      colorTextSecondary: css('--text-secondary', '#5B6778'),
      colorTextTertiary: css('--text-tertiary', '#8894A4'),
      colorTextLightSolid: css('--text-on-accent', '#ffffff'),
      colorBorder: css('--border-default', '#e5e7eb'),
      colorBorderSecondary: css('--bg-elevated', '#F3F5F7'),
      borderRadius: parseInt(css('--radius-md', '8px'), 10),
      borderRadiusSM: parseInt(css('--radius-sm', '4px'), 10),
      borderRadiusLG: parseInt(css('--radius-xl', '12px'), 10),
      borderRadiusXS: 2,
      fontFamily: css(
        '--font-sans',
        'Inter, "SF Pro Display", -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif',
      ),
      fontFamilyCode: css(
        '--font-mono',
        '"JetBrains Mono", "SF Mono", "Fira Code", "Cascadia Code", monospace',
      ),
      controlHeight: 36,
      controlHeightSM: 30,
      controlHeightLG: 44,
    },
    components: {
      Table: {
        headerBg: 'transparent',
        headerColor: css('--text-tertiary', '#8894A4'),
        headerSplitColor: 'transparent',
        rowHoverBg: css('--bg-hover', 'rgba(0, 0, 0, 0.03)'),
        borderColor: css('--border-default', '#e5e7eb'),
        cellPaddingInline: 16,
        cellPaddingBlock: 14,
        headerBorderRadius: 0,
      },
      Button: {
        borderRadius: parseInt(css('--radius-md', '8px'), 10),
        borderRadiusSM: parseInt(css('--radius-sm', '4px'), 10),
        primaryShadow: 'none',
      },
      Card: {
        borderRadius: parseInt(css('--card-radius', '12px'), 10),
        borderRadiusLG: parseInt(css('--radius-2xl', '16px'), 10),
        colorBgContainer: css('--card-bg', '#ffffff'),
      },
      Modal: {
        borderRadiusLG: parseInt(css('--radius-xl', '12px'), 10),
        colorBgElevated: css('--bg-elevated', '#F3F5F7'),
      },
      Drawer: {
        colorBgElevated: css('--bg-elevated', '#F3F5F7'),
      },
      Tag: {
        borderRadiusSM: parseInt(css('--radius-sm', '4px'), 10),
        defaultBg: css('--bg-surface', '#EDF0F3'),
        defaultColor: css('--text-secondary', '#5B6778'),
      },
      Input: {
        borderRadius: parseInt(css('--radius-md', '8px'), 10),
        colorBgContainer: css('--bg-input', '#ffffff'),
        activeBorderColor: css('--accent', '#2563EB'),
        activeShadow: `0 0 0 2px ${css('--accent-glow', 'rgba(37, 99, 235, 0.12)')}`,
      },
      Select: {
        borderRadius: parseInt(css('--radius-md', '8px'), 10),
        colorBgContainer: css('--bg-input', '#ffffff'),
        optionSelectedBg: css('--accent-dim', 'rgba(37, 99, 235, 0.08)'),
        optionSelectedColor: css('--accent', '#2563EB'),
      },
      Tabs: {
        inkBarColor: css('--accent', '#2563EB'),
        itemSelectedColor: css('--text-primary', '#0F1115'),
        itemHoverColor: css('--text-secondary', '#5B6778'),
        itemColor: css('--text-tertiary', '#8894A4'),
      },
      Alert: {
        colorError: css('--color-error', '#E5484D'),
        colorErrorBg: css('--color-error-dim', 'rgba(229, 72, 77, 0.08)'),
        colorErrorBorder: css('--color-error-border', 'rgba(229, 72, 77, 0.20)'),
        colorWarning: css('--color-warning', '#F0B100'),
        colorWarningBg: css('--color-warning-dim', 'rgba(240, 177, 0, 0.08)'),
        colorWarningBorder: css('--color-warning-border', 'rgba(240, 177, 0, 0.20)'),
        colorSuccess: css('--color-success', '#30A46C'),
        colorSuccessBg: css('--color-success-dim', 'rgba(48, 164, 108, 0.08)'),
        colorSuccessBorder: css('--color-success-border', 'rgba(48, 164, 108, 0.20)'),
        colorInfo: css('--color-info', '#2563EB'),
        colorInfoBg: css('--accent-dim', 'rgba(37, 99, 235, 0.08)'),
        colorInfoBorder: css('--accent-border', 'rgba(37, 99, 235, 0.20)'),
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
